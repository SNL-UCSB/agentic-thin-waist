"""
merge.py — Merge operation: combine all /32 leaf CTPs under a subnet across a
window range into a single merged CTP with output PCAPs.

The merge endpoint:
1. Queries all /32 leaf CTPs for the given dataset/subnet across
   ``[start_index, end_index]`` windows to collect leaf IPs.
2. Gathers every ``window_XXXX.pcap`` for each leaf IP and direction.
3. Merges all PCAPs with ``joincap`` (batched to avoid ARG_MAX limits).
4. Reorders merged PCAPs with ``reordercap``.
5. Computes timeseries and metrics from the merged PCAPs.
6. Stores the merged CTP in the database and returns it.

Output layout::

    <output_dir>/<dataset_name>_merged/
        downlink/<ctp_id>_download.pcap
        uplink/<ctp_id>_upload.pcap
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.config import Settings, get_settings
from app.database.postgres import Database
from app.models.ctp import (
    CTPStructure,
    CrossTrafficProfile,
)
from app.operations.extract import build_timeseries_from_window
from app.operations.metrics import compute_all_metrics
from app.pcap_utils import (
    _reorder_single_pcap,
)

logger = logging.getLogger(__name__)

_JOINCAP_BATCH_SIZE = 30


class CTPMerger:
    """Merge all leaf CTPs under a subnet across a window range.

    Args:
        db: Initialised :class:`~app.database.postgres.Database` instance.
        settings: Runtime configuration.
    """

    def __init__(self, db: Database, settings: Optional[Settings] = None) -> None:
        self._db = db
        self._cfg = settings or get_settings()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def merge_subnet_range(
        self,
        dataset_name: str,
        subnet: str,
        start_index: int,
        end_index: int,
        output_dir: str,
        users_root: str,
    ) -> Tuple[CrossTrafficProfile, Path, Path]:
        """Merge all /32 leaf CTPs under *subnet* across windows
        ``[start_index, end_index]``.

        Args:
            dataset_name: Dataset label.
            subnet: Parent CIDR subnet (e.g. ``'169.231.10.0/24'``).
            start_index: First window index to include (inclusive).
            end_index: Last window index to include (inclusive).
            output_dir: Root for output PCAP directories.
            users_root: Root of the per-user PCAP directory tree produced
                during extraction.

        Returns:
            Tuple of ``(merged_ctp, download_pcap_path, upload_pcap_path)``.

        Raises:
            ValueError: If no leaf CTPs are found for the given parameters.
        """
        # 1. Get all leaf CTPs to collect unique IPs
        leaf_ctps = self._db.get_leaf_ctps_for_subnet_range(
            dataset_name, subnet, start_index, end_index
        )
        if not leaf_ctps:
            raise ValueError(
                f"No /32 leaf CTPs found for dataset='{dataset_name}' "
                f"subnet='{subnet}' windows {start_index}–{end_index}."
            )

        leaf_ips = sorted({str(c.subnet).split("/")[0] for c in leaf_ctps})
        contributor_count = len(leaf_ips)
        duration = (end_index - start_index + 1) * leaf_ctps[0].duration_seconds

        # 2. Build output paths
        safe_subnet = subnet.replace("/", "_").replace(".", "-")
        ctp_id = f"ctp-merged-{dataset_name}-{safe_subnet}-{start_index}-{end_index}"
        dataset_out = Path(output_dir) / f"{dataset_name}_merged"
        downlink_dir = dataset_out / "downlink"
        uplink_dir = dataset_out / "uplink"
        downlink_dir.mkdir(parents=True, exist_ok=True)
        uplink_dir.mkdir(parents=True, exist_ok=True)

        download_pcap = downlink_dir / f"{ctp_id}_download.pcap"
        upload_pcap = uplink_dir / f"{ctp_id}_upload.pcap"

        # 3. Merge + reorder PCAPs for each direction
        for pcap_path, direction in (
            (download_pcap, "download"),
            (upload_pcap, "upload"),
        ):
            self._join_pcaps_for_range(
                leaf_ips=leaf_ips,
                start_index=start_index,
                end_index=end_index,
                users_root=Path(users_root),
                output_path=pcap_path,
                direction=direction,
            )
            if pcap_path.exists():
                _reorder_single_pcap(pcap_path)

        # 4. Compute timeseries and metrics from merged PCAPs
        bin_ms = self._cfg.burst_interval_ms
        bin_sec = bin_ms / 1000.0

        download_ts = build_timeseries_from_window(
            download_pcap, bin_width_ms=bin_ms, window_sec=duration
        )
        upload_ts = build_timeseries_from_window(
            upload_pcap, bin_width_ms=bin_ms, window_sec=duration
        )

        intensity, burstiness, correlation, _ = compute_all_metrics(
            upload_ts=upload_ts,
            download_ts=download_ts,
            bin_width_sec=bin_sec,
            contributor_ips=leaf_ips,
        )

        total_upload = float(np.sum(upload_ts))
        total_download = float(np.sum(download_ts))
        structure = CTPStructure(
            contributor_count=contributor_count,
            unique_source_ips=contributor_count,
            unique_dest_ips=contributor_count,
            upload_download_ratio=(
                total_upload / total_download if total_download > 0 else -1.0
            ),
            prefix_diversity=leaf_ctps[0].structure.prefix_diversity,
        )

        # 5. Build and store merged CTP
        merged = CrossTrafficProfile(
            ctp_id=ctp_id,
            dataset_name=dataset_name,
            subnet=subnet,
            window_index=start_index,
            extracted_from=f"{dataset_name}/{subnet}/windows_{start_index}-{end_index}",
            duration_seconds=duration,
            upload_timeseries=upload_ts.tolist(),
            download_timeseries=download_ts.tolist(),
            intensity=intensity,
            burstiness=burstiness,
            temporal_correlation=correlation,
            structure=structure,
            is_merged=True,
            merge_start_index=start_index,
            merge_end_index=end_index,
            download_pcap=str(download_pcap),
            upload_pcap=str(upload_pcap),
        )
        self._db.upsert_ctp(merged)
        logger.info(
            "Merged %d leaf IP(s) windows %d–%d → '%s'  intensity=%.2f Mbps",
            contributor_count,
            start_index,
            end_index,
            ctp_id,
            merged.intensity.mean_mbps,
        )
        return merged, download_pcap, upload_pcap

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _join_pcaps_for_range(
        self,
        leaf_ips: List[str],
        start_index: int,
        end_index: int,
        users_root: Path,
        output_path: Path,
        direction: str,
    ) -> None:
        """Batch-merge per-user window PCAPs using ``joincap``.

        Processes IPs in batches of :data:`_JOINCAP_BATCH_SIZE` to stay
        within ``ARG_MAX``.  Each batch's output is accumulated into
        *output_path* by feeding the previous result back into the next
        ``joincap`` invocation via a temporary file.

        PCAP files are located at::

            <users_root>/<ip>/<direction>/windows/window_XXXX.pcap

        Args:
            leaf_ips: Sorted list of /32 IP address strings.
            start_index: First window index (inclusive).
            end_index: Last window index (inclusive).
            users_root: Root of the per-user PCAP directory tree.
            output_path: Destination merged PCAP path.
            direction: ``'download'`` or ``'upload'``.
        """
        tmp_path = output_path.with_suffix(".tmp.pcap")

        valid_patterns = {
            f"window_{w:04d}.pcap" for w in range(start_index, end_index + 1)
        }

        for batch_start in range(0, len(leaf_ips), _JOINCAP_BATCH_SIZE):
            batch_ips = leaf_ips[batch_start : batch_start + _JOINCAP_BATCH_SIZE]

            pcap_files: List[str] = []
            for ip in batch_ips:
                base = users_root / ip / direction / "windows"

                # Recursively find matching PCAPs
                for p in base.rglob("window_*.pcap"):
                    if p.name in valid_patterns:
                        pcap_files.append(str(p))

            if not pcap_files:
                continue

            pcap_files = sorted(set(pcap_files))

            # Accumulate previous batch result into current joincap call
            if batch_start != 0 and output_path.exists():
                output_path.rename(tmp_path)
                pcap_files.append(str(tmp_path))

            cmd = ["joincap", "-w", str(output_path)] + pcap_files
            logger.debug(
                "joincap: %d %s PCAP(s) → '%s'", len(pcap_files), direction, output_path
            )
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error("joincap stderr: %s", result.stderr)
                    raise subprocess.CalledProcessError(
                        result.returncode, cmd, result.stdout, result.stderr
                    )
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

        if not output_path.exists():
            logger.warning(
                "No %s PCAP files found for windows %d–%d; output not created.",
                direction,
                start_index,
                end_index,
            )
