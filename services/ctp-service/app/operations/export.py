"""
export.py — Export operation: produce replay-ready PCAP data for Substrate Worker.

The export operation retrieves a stored CTP, locates the per-user window PCAP
files that were produced during extraction, and returns the paths to the
merged upload and download PCAPs.

If the merged PCAPs already exist on disk (produced by a prior
:mod:`~app.operations.transform` call), they are returned directly.
Otherwise the PCAPs are merged on-the-fly from the per-user window files.

The Substrate Worker uses the returned PCAPs with ``tcpreplay`` to apply the
CTP at a bottleneck interface.

Output layout
~~~~~~~~~~~~~
.. code-block:: text

    <replay_dir>/<dataset_name>/
        downlink/
            <ctp_id>_download.pcap
        uplink/
            <ctp_id>_upload.pcap
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from app.config import Settings, get_settings
from app.database.postgres import Database
from app.models.ctp import CrossTrafficProfile
from app.pcap_utils import (
    _reorder_single_pcap,
)

logger = logging.getLogger(__name__)


class CTPExporter:
    """Generate replay-ready PCAP files from stored CTP descriptors.

    Args:
        db: Initialised :class:`~app.database.postgres.Database` instance.
        settings: Runtime configuration.
    """

    def __init__(self, db: Database, settings: Optional[Settings] = None) -> None:
        self._db = db
        self._cfg = settings or get_settings()

    def export_replay_pcap(
        self,
        ctp_id: str,
        replay_dir: str,
        users_root: str,
    ) -> Tuple[Path, Path]:
        """Produce or locate replay-ready PCAP files for a CTP.

        Algorithm:

        1. Load the CTP from the corpus.
        2. Check if merged PCAPs already exist in *replay_dir*.
        3. If not, resolve the /32 leaf children, collect their per-window
           PCAP files, and merge them with ``joincap``.
        4. Return ``(download_pcap, upload_pcap)`` paths.

        Args:
            ctp_id: Unique CTP identifier.
            replay_dir: Root directory for replay-ready PCAP output.
            users_root: Root of the per-user PCAP tree (produced by Step 1).

        Returns:
            Tuple ``(download_pcap_path, upload_pcap_path)``.

        Raises:
            ValueError: If the CTP is not found or PCAP merging fails.
        """
        ctp = self._db.get_ctp(ctp_id)
        if ctp is None:
            raise ValueError(f"CTP '{ctp_id}' not found in corpus.")

        safe_id = ctp_id.replace("/", "_").replace(":", "-")
        dataset_out = Path(replay_dir) / f"{ctp.dataset_name}_replay"
        downlink_dir = dataset_out / "downlink"
        uplink_dir = dataset_out / "uplink"
        downlink_dir.mkdir(parents=True, exist_ok=True)
        uplink_dir.mkdir(parents=True, exist_ok=True)

        download_pcap = downlink_dir / f"{safe_id}_download.pcap"
        upload_pcap = uplink_dir / f"{safe_id}_upload.pcap"

        # Return cached files if they already exist
        if download_pcap.exists() and upload_pcap.exists():
            logger.info(
                "Replay PCAPs already exist for '%s'; returning cached files.", ctp_id
            )
            return download_pcap, upload_pcap

        # Resolve leaf user IPs
        leaf_ctps = self._db.get_leaf_ctps_for_subnet(
            ctp.dataset_name, ctp.subnet, ctp.window_index
        )
        leaf_ips = [str(c.subnet).split("/")[0] for c in leaf_ctps]

        if not leaf_ips:
            raise ValueError(
                f"No /32 leaf CTPs found for CTP '{ctp_id}' "
                f"(subnet={ctp.subnet}, window={ctp.window_index})."
            )

        # Merge per-user window PCAPs
        for direction, out_path in [
            ("download", download_pcap),
            ("upload", upload_pcap),
        ]:
            pcap_files = _collect_window_pcaps(
                leaf_ips=leaf_ips,
                window_index=ctp.window_index,
                users_root=Path(users_root),
                direction=direction,
            )
            if pcap_files:
                _joincap_merge(pcap_files, out_path)
                _reorder_single_pcap(out_path)
            else:
                logger.warning(
                    "No %s PCAPs found for CTP '%s'; output will be missing.",
                    direction,
                    ctp_id,
                )

        logger.info(
            "Exported replay PCAPs for '%s': download=%s  upload=%s",
            ctp_id,
            download_pcap,
            upload_pcap,
        )
        return download_pcap, upload_pcap

    def get_ctp(self, ctp_id: str) -> Optional[CrossTrafficProfile]:
        """Fetch a CTP from the corpus.

        Args:
            ctp_id: CTP identifier.

        Returns:
            :class:`~app.models.ctp.CrossTrafficProfile` or ``None``.
        """
        return self._db.get_ctp(ctp_id)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _collect_window_pcaps(
    leaf_ips: List[str],
    window_index: int,
    users_root: Path,
    direction: str,
) -> List[str]:
    """Collect all per-user PCAP files for a given window and direction.

    Searches under ``<users_root>/<ip>/<direction>/windows/**/window_XXXX.pcap``
    for each leaf IP.

    Args:
        leaf_ips: List of /32 IP address strings.
        window_index: 1-based window index.
        users_root: Root of the per-user directory tree.
        direction: ``'upload'`` or ``'download'``.

    Returns:
        Sorted list of PCAP file path strings.
    """
    pattern = f"window_{window_index:04d}.pcap"
    paths: List[str] = []
    for ip in leaf_ips:
        base = users_root / ip / direction / "windows"
        if base.exists():
            paths.extend(str(m) for m in sorted(base.rglob(pattern)))
    return paths


def _joincap_merge(pcap_files: List[str], output_path: Path) -> None:
    """Merge a list of PCAP files into *output_path* using ``joincap``.

    Args:
        pcap_files: Input PCAP paths (passed directly to joincap).
        output_path: Destination merged PCAP path.

    Raises:
        subprocess.CalledProcessError: If joincap returns a non-zero exit code.
    """
    cmd = ["joincap", "-w", str(output_path)] + pcap_files
    logger.debug("joincap: merging %d file(s) → '%s'", len(pcap_files), output_path)
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        msg = exc.stderr.decode(errors="replace") if exc.stderr else str(exc)
        logger.error("joincap failed: %s", msg)
        raise
