"""
extract.py — Extract operation: PCAP traces → CTP corpus in PostgreSQL.

This module orchestrates the full six-step extraction pipeline described in
the system design:

1. **Split PCAPs by internal IP** (:mod:`~app.operations.pcap_split`)
   - Gateway PCAP(s) → per-user upload/download PCAPs

2. **Split by time windows** (:mod:`~app.operations.window_split`)
   - Per-user PCAPs → ``window_XXXX.pcap`` files (default 30 s)

3. **Build timeseries** (this module + :mod:`~app.operations.metrics`)
   - Per-user per-window PCAP → byte-count array at 100 ms resolution

4. **Build prefix-hierarchical trees** (:mod:`~app.trees`)
   - Per-window user timeseries → TreeNode hierarchy (/32 → /16)

5. **Store in PostgreSQL** (:mod:`~app.database.postgres`)
   - Every tree node → row in ``ctp_nodes``

6. **Return CTP list** — list of stored :class:`~app.models.ctp.CrossTrafficProfile`

Usage
~~~~~
.. code-block:: python

    from app.operations.extract import Extractor
    from app.database.postgres import Database
    from app.config import get_settings

    cfg = get_settings()
    db  = Database(cfg.database_url)
    db.initialize()

    extractor = Extractor(db=db, settings=cfg)
    ctps = extractor.run(
        pcap_input="/data/gateway-trace.pcap",
        output_dir="/data/ctp-working",
        dataset_name="ucsb-2026-03-04",
    )
    print(f"Extracted {len(ctps)} CTPs")
"""

from __future__ import annotations

import ipaddress
import logging
import multiprocessing as mp
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scapy.layers.inet import IP
from scapy.utils import PcapReader

from app.config import Settings, get_settings
from app.database.postgres import Database
from app.models.ctp import CrossTrafficProfile
from app.operations.metrics import compute_all_metrics
from app.operations.pcap_split import collect_pcap_inputs, split_pcaps_parallel
from app.operations.window_split import split_all_users_parallel
from app.tree_node import TreeNode
from app.time_series_modules import Fragment
from app.trees import (
    construct_trees,
    filter_users,
    post_process_trees,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Timeseries building from pre-split window PCAPs
# ---------------------------------------------------------------------------


def build_timeseries_from_window(
    pcap_path: Path,
    bin_width_ms: int = 100,
    window_sec: int = 30,
) -> np.ndarray:
    """Read a single window PCAP and bin packet sizes into a byte-count array.

    Packets are binned by their IP-header length (``ip.len``) rather than
    the captured payload, so truncated captures still produce correct byte
    counts.

    Args:
        pcap_path: Path to a ``window_XXXX.pcap`` file.
        bin_width_ms: Bin width in milliseconds (default 100 ms).
        window_sec: Window duration in seconds (determines array length).

    Returns:
        1-D NumPy array of byte counts; length = ``window_sec * 1000 / bin_width_ms``.
        Returns a zero array if the file is empty or has no IP packets.
    """
    n_bins = int(window_sec * 1000 // bin_width_ms)
    ts = np.zeros(n_bins, dtype=np.float64)

    if not pcap_path.exists():
        return ts

    start_time: Optional[float] = None
    with PcapReader(str(pcap_path)) as reader:
        for pkt in reader:
            if not pkt.haslayer(IP):
                continue
            pkt_time = float(pkt.time)
            ip_len = pkt[IP].len  # use IP header length, not captured length

            if start_time is None:
                start_time = pkt_time

            elapsed_ms = (pkt_time - start_time) * 1000
            idx = int(elapsed_ms // bin_width_ms)
            if 0 <= idx < n_bins:
                ts[idx] += ip_len

    return ts


def _build_user_timeseries_worker(args: Tuple) -> Optional[Tuple[str, int, np.ndarray, np.ndarray]]:
    """Worker: compute upload + download timeseries for one (user, window_index).

    Returns:
        ``(ip_str, window_index, upload_ts, download_ts)`` or ``None`` on error.
    """
    ip_str, window_index, upload_pcap, download_pcap, bin_width_ms, window_sec = args
    try:
        upload_ts = build_timeseries_from_window(
            Path(upload_pcap), bin_width_ms=bin_width_ms, window_sec=window_sec
        )
        download_ts = build_timeseries_from_window(
            Path(download_pcap), bin_width_ms=bin_width_ms, window_sec=window_sec
        )
        return ip_str, window_index, upload_ts, download_ts
    except Exception as exc:
        logger.error("Timeseries build failed for IP=%s window=%d: %s", ip_str, window_index, exc)
        return None


# ---------------------------------------------------------------------------
# TreeNode → CrossTrafficProfile conversion
# ---------------------------------------------------------------------------


def _tree_node_to_ctp(
    node: TreeNode,
    dataset_name: str,
    window_index: int,
    duration_seconds: int,
    bin_width_sec: float,
    contributor_ips: List[str],
    extracted_from: str = "",
) -> CrossTrafficProfile:
    """Convert a :class:`~app.tree_node.TreeNode` to a :class:`~app.models.ctp.CrossTrafficProfile`.

    Args:
        node: TreeNode with pre-computed fragments.
        dataset_name: Dataset label.
        window_index: Zero-based time-window index.
        duration_seconds: Window duration.
        bin_width_sec: Bin width in seconds (used for rate computation).
        contributor_ips: /32 leaf IP strings under this node.
        extracted_from: Source PCAP path(s) string.

    Returns:
        Fully populated :class:`~app.models.ctp.CrossTrafficProfile`.
    """
    upload_ts = node.upload_fragment.container.astype(float)
    download_ts = node.download_fragment.container.astype(float)

    intensity, burstiness, correlation, structure = compute_all_metrics(
        upload_ts=upload_ts,
        download_ts=download_ts,
        bin_width_sec=bin_width_sec,
        contributor_ips=contributor_ips,
    )

    subnet_str = str(node.network)
    ctp_id = f"ctp-{dataset_name}-{subnet_str.replace('/', '_')}-w{window_index:04d}"

    return CrossTrafficProfile(
        ctp_id=ctp_id,
        dataset_name=dataset_name,
        subnet=subnet_str,
        window_index=window_index,
        extracted_from=extracted_from,
        duration_seconds=duration_seconds,
        upload_timeseries=upload_ts.tolist(),
        download_timeseries=download_ts.tolist(),
        intensity=intensity,
        burstiness=burstiness,
        temporal_correlation=correlation,
        structure=structure,
    )


def _collect_all_nodes(root: TreeNode) -> List[TreeNode]:
    """DFS traversal; return all nodes in the subtree including root."""
    nodes: List[TreeNode] = []
    stack = [root]
    visited = set()
    while stack:
        node = stack.pop()
        if id(node) in visited:
            continue
        visited.add(id(node))
        nodes.append(node)
        stack.extend(node.children)
    return nodes


# ---------------------------------------------------------------------------
# Main Extractor class
# ---------------------------------------------------------------------------


class Extractor:
    """Orchestrates the full PCAP → CTP extraction pipeline.

    Args:
        db: Initialised :class:`~app.database.postgres.Database` instance.
        settings: Runtime configuration.  Defaults to :func:`~app.config.get_settings`.
    """

    def __init__(
        self,
        db: Database,
        settings: Optional[Settings] = None,
    ) -> None:
        self._db = db
        self._cfg = settings or get_settings()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def run(
        self,
        pcap_input: str,
        output_dir: str,
        dataset_name: str,
        *,
        window_duration_sec: Optional[int] = None,
        burst_interval_ms: Optional[int] = None,
        internal_subnets: Optional[List[str]] = None,
        workers: Optional[int] = None,
        start_time_epoch: Optional[float] = None,
    ) -> List[CrossTrafficProfile]:
        """Run the full extract pipeline for one dataset.

        Args:
            pcap_input: Path to a PCAP file or directory of PCAPs.
            output_dir: Root directory for intermediate per-user files.
            dataset_name: Human-readable label for this dataset.
            window_duration_sec: Override configured window size.
            burst_interval_ms: Override configured bin width.
            internal_subnets: Override configured subnet prefixes.
            workers: Override configured worker count.
            start_time_epoch: Optional epoch timestamp of capture start.

        Returns:
            List of all :class:`~app.models.ctp.CrossTrafficProfile` objects
            stored in the database during this run.
        """
        cfg = self._cfg
        window_sec = window_duration_sec or cfg.window_duration_sec
        bin_ms = burst_interval_ms or cfg.burst_interval_ms
        subnets = internal_subnets or cfg.internal_subnets
        n_workers = workers or cfg.workers
        bin_sec = bin_ms / 1000.0

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        pcap_paths = collect_pcap_inputs(Path(pcap_input))
        logger.info(
            "[Extract] Dataset='%s' | %d PCAP(s) | window=%ds | bin=%dms | workers=%d",
            dataset_name,
            len(pcap_paths),
            window_sec,
            bin_ms,
            n_workers,
        )

        # ---- Step 1: Split by internal IP ----
        logger.info("[Step 1] Splitting by internal IP...")
        split_pcaps_parallel(pcap_paths, output_path, subnets, workers=n_workers)
        users_root = output_path / "users"

        # ---- Step 2: Split by time windows ----
        logger.info("[Step 2] Splitting into %d-second windows...", window_sec)
        split_all_users_parallel(users_root, window_sec=window_sec, workers=n_workers)

        # ---- Steps 3–5: Timeseries → Trees → DB ----
        logger.info("[Steps 3-5] Building timeseries, trees, and storing CTPs...")
        all_ctps = self._build_and_store_trees(
            users_root=users_root,
            dataset_name=dataset_name,
            window_sec=window_sec,
            bin_ms=bin_ms,
            bin_sec=bin_sec,
            n_workers=n_workers,
            extracted_from=str(pcap_input),
        )

        # ---- Update dataset metadata ----
        user_dirs = [d for d in users_root.iterdir() if d.is_dir()]
        self._db.upsert_dataset(
            dataset_name=dataset_name,
            pcap_source=str(pcap_input),
            window_duration_sec=window_sec,
            burst_interval_ms=bin_ms,
            gateway_subnet=cfg.gateway_subnet,
            total_windows=self._count_windows(users_root),
            total_users=len(user_dirs),
        )

        logger.info(
            "[Extract] Complete — %d CTPs stored for dataset '%s'.",
            len(all_ctps),
            dataset_name,
        )
        return all_ctps

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _build_and_store_trees(
        self,
        users_root: Path,
        dataset_name: str,
        window_sec: int,
        bin_ms: int,
        bin_sec: float,
        n_workers: int,
        extracted_from: str,
    ) -> List[CrossTrafficProfile]:
        """Build per-window prefix trees and store all nodes in the DB.

        For each time-window index found across all users:
        1. Load each user's upload/download timeseries for that window.
        2. Create Fragment objects and build the TreeNode hierarchy.
        3. Convert every tree node to a CTP and store in PostgreSQL.

        Args:
            users_root: ``<output_dir>/users/`` directory.
            dataset_name: Dataset label.
            window_sec: Window duration.
            bin_ms: Bin width in ms.
            bin_sec: Bin width in seconds.
            n_workers: Worker count.
            extracted_from: Source PCAP path string.

        Returns:
            All stored :class:`~app.models.ctp.CrossTrafficProfile` objects.
        """
        # Discover all users and the maximum window index
        user_dirs = sorted(d for d in users_root.iterdir() if d.is_dir())
        if not user_dirs:
            logger.warning("No user directories found under '%s'.", users_root)
            return []

        max_window = self._find_max_window_index(user_dirs)
        logger.info("Found %d users and %d time window(s).", len(user_dirs), max_window)

        all_ctps: List[CrossTrafficProfile] = []

        # Process one window at a time to bound memory usage
        for window_idx in range(1, max_window + 1):
            ctps = self._process_window(
                user_dirs=user_dirs,
                window_index=window_idx,
                dataset_name=dataset_name,
                window_sec=window_sec,
                bin_ms=bin_ms,
                bin_sec=bin_sec,
                n_workers=n_workers,
                extracted_from=extracted_from,
            )
            all_ctps.extend(ctps)

        return all_ctps

    def _process_window(
        self,
        user_dirs: List[Path],
        window_index: int,
        dataset_name: str,
        window_sec: int,
        bin_ms: int,
        bin_sec: float,
        n_workers: int,
        extracted_from: str,
    ) -> List[CrossTrafficProfile]:
        """Build and store the prefix tree for a single time window.

        Args:
            user_dirs: List of per-user directories.
            window_index: 1-based window index.
            dataset_name: Dataset label.
            window_sec: Window duration in seconds.
            bin_ms: Bin width in milliseconds.
            bin_sec: Bin width in seconds.
            n_workers: Worker count.
            extracted_from: Source PCAP string.

        Returns:
            List of CTPs stored for this window.
        """
        n_bins = int(window_sec * 1000 // bin_ms)

        # Build args list for parallel timeseries computation
        worker_args = []
        for user_dir in user_dirs:
            ip_str = user_dir.name
            upload_pcap = user_dir / "upload" / "windows" / "*.pcap"
            # Resolve glob for this specific window index
            upload_path = self._window_pcap_path(user_dir, "upload", window_index)
            download_path = self._window_pcap_path(user_dir, "download", window_index)
            worker_args.append(
                (
                    ip_str,
                    window_index,
                    str(upload_path),
                    str(download_path),
                    bin_ms,
                    window_sec,
                )
            )

        # Compute timeseries in parallel
        with mp.Pool(processes=n_workers) as pool:
            results = pool.map(_build_user_timeseries_worker, worker_args)

        # Filter failed results
        valid = [r for r in results if r is not None]
        if not valid:
            return []

        # Build user → timeseries mapping
        user_ts: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
        for ip_str, _w_idx, upload_ts, download_ts in valid:
            user_ts[ip_str] = (upload_ts, download_ts)

        # Create leaf TreeNode objects
        leaf_nodes: List[TreeNode] = []
        for ip_str, (upload_ts, download_ts) in user_ts.items():
            try:
                network = ipaddress.IPv4Network(f"{ip_str}/32")
            except ValueError:
                continue

            # Wrap numpy arrays in Fragment objects for tree compatibility
            dl_frag = Fragment.__new__(Fragment)
            dl_frag.container = download_ts.copy()
            ul_frag = Fragment.__new__(Fragment)
            ul_frag.container = upload_ts.copy()

            node = TreeNode.from_parameters(
                network=network,
                download_fragment=dl_frag,
                upload_fragment=ul_frag,
                fwd_packets=0,
                bwd_packets=0,
            )
            leaf_nodes.append(node)

        if not leaf_nodes:
            return []

        # Build hierarchy: /32 → /31 → ... → /16 → /0
        top_prefix = self._cfg.top_prefix_len
        current_nodes = leaf_nodes

        for prefix_len in range(31, top_prefix - 1, -1):
            current_nodes = self._aggregate_nodes(current_nodes, prefix_len)

        # Wrap under single /0 root
        root_net = ipaddress.ip_network("0.0.0.0/0")
        root_nodes = self._aggregate_nodes(current_nodes, 0, root_net)
        if not root_nodes:
            return []

        root = root_nodes[0]

        # Convert all tree nodes to CTPs and store
        all_nodes = _collect_all_nodes(root)
        ctps: List[CrossTrafficProfile] = []

        for node in all_nodes:
            contributor_ips = [
                str(leaf.network.network_address) for leaf in TreeNode.get_leaf_nodes(node)
            ]
            ctp = _tree_node_to_ctp(
                node=node,
                dataset_name=dataset_name,
                window_index=window_index,
                duration_seconds=window_sec,
                bin_width_sec=bin_sec,
                contributor_ips=contributor_ips,
                extracted_from=extracted_from,
            )
            ctps.append(ctp)

        self._db.upsert_ctps_bulk(ctps)
        logger.debug(
            "Window %d: stored %d CTP nodes (%d users).",
            window_index,
            len(ctps),
            len(leaf_nodes),
        )
        return ctps

    @staticmethod
    def _aggregate_nodes(
        nodes: List[TreeNode],
        new_prefix: int,
        fixed_network: Optional[ipaddress.IPv4Network] = None,
    ) -> List[TreeNode]:
        """Group nodes by parent subnet and aggregate into parent TreeNodes.

        Args:
            nodes: Current-level TreeNode list.
            new_prefix: Target prefix length for grouping.
            fixed_network: When set, all nodes are grouped under this single
                network (used for the root /0 aggregation).

        Returns:
            List of parent TreeNode objects.
        """
        from collections import defaultdict

        groups: Dict[ipaddress.IPv4Network, List[TreeNode]] = defaultdict(list)

        for node in nodes:
            if fixed_network is not None:
                parent = fixed_network
            else:
                parent = ipaddress.ip_network(node.network).supernet(new_prefix=new_prefix)
            groups[parent].append(node)

        parent_nodes: List[TreeNode] = []
        for parent_net, children in groups.items():
            dl = Fragment.__new__(Fragment)
            ul = Fragment.__new__(Fragment)
            dl.container = sum(
                (c.download_fragment.container for c in children),
                np.zeros_like(children[0].download_fragment.container),
            )
            ul.container = sum(
                (c.upload_fragment.container for c in children),
                np.zeros_like(children[0].upload_fragment.container),
            )
            fwd = sum(c.fwd_packets for c in children)
            bwd = sum(c.bwd_packets for c in children)
            parent_node = TreeNode.from_parameters(parent_net, dl, ul, fwd, bwd, children)
            parent_nodes.append(parent_node)

        return parent_nodes

    @staticmethod
    def _window_pcap_path(user_dir: Path, direction: str, window_index: int) -> Path:
        """Locate the PCAP file for a given user, direction, and window index.

        Searches under ``<user_dir>/<direction>/windows/*/window_XXXX.pcap``.
        Returns a non-existent path if not found (caller handles missing files).

        Args:
            user_dir: User's root directory.
            direction: ``'upload'`` or ``'download'``.
            window_index: 1-based window index.

        Returns:
            Path to the window PCAP (may not exist).
        """
        windows_root = user_dir / direction / "windows"
        pattern = f"*/window_{window_index:04d}.pcap"
        matches = sorted(windows_root.glob(pattern))
        return matches[0] if matches else windows_root / f"window_{window_index:04d}.pcap"

    @staticmethod
    def _find_max_window_index(user_dirs: List[Path]) -> int:
        """Return the highest window index found across all user directories.

        Args:
            user_dirs: List of per-user directories.

        Returns:
            Maximum window index (1-based).  Returns 0 if none found.
        """
        max_idx = 0
        for user_dir in user_dirs:
            for direction in ("upload", "download"):
                windows_root = user_dir / direction / "windows"
                for pcap in windows_root.rglob("window_*.pcap"):
                    try:
                        idx = int(pcap.stem.split("_")[1])
                        max_idx = max(max_idx, idx)
                    except (IndexError, ValueError):
                        continue
        return max_idx

    @staticmethod
    def _count_windows(users_root: Path) -> int:
        """Count the total number of window PCAP files across all users."""
        return sum(1 for _ in users_root.rglob("window_*.pcap"))
