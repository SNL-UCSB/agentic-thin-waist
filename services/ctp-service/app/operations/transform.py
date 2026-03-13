"""
transform.py — Transform operation: adapt a CTP to a target bottleneck capacity.

The transform operation:

1. Loads the source CTP from the corpus (via :class:`~app.database.postgres.Database`).
2. Resolves all /32 leaf children of the CTP's subnet and window.
3. Locates the corresponding per-window PCAP files on disk.
4. Merges the PCAPs for all leaf users (upload and download separately) using
   ``joincap`` (delegated to :func:`~app.pcap_utils.merge_pcaps_by_index`).
5. Reorders packets with ``reordercap``
   (:func:`~app.pcap_utils.reorder_pcap_files`).
6. Pads packets to their IP-header-reported size
   (:func:`~app.pcap_utils.pad_pcap_frames`).
7. Optionally trims bursts to a target throughput threshold
   (:func:`~app.pcap_utils.trim_pcap_by_rate`).
8. Returns paths to the final ``merged_download.pcap`` and
   ``merged_upload.pcap`` files, and stores the transformed CTP descriptor.

Amplitude scaling
~~~~~~~~~~~~~~~~~
Only the *intensity descriptors* (mean/peak bps, pps) are scaled by the
factor ``target_capacity / original_intensity``.  Burstiness, temporal
correlation, and structural attributes are preserved unchanged.

Output layout
~~~~~~~~~~~~~
.. code-block:: text

    <output_dir>/<dataset_name>/
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
from app.models.ctp import CTPIntensity, CrossTrafficProfile
from app.pcap_utils import (
    merge_pcaps_by_index,
    pad_pcap_frames,
    reorder_pcap_files,
    trim_pcap_by_rate,
)

logger = logging.getLogger(__name__)

# Threshold for burst trimming: 100 ms interval, 6 Mbps → bytes per interval
_DEFAULT_TRIM_INTERVAL_SEC = 0.1


class CTPTransformer:
    """Adapt CTP amplitude to a target bottleneck capacity.

    Args:
        db: Initialised :class:`~app.database.postgres.Database` instance.
        settings: Runtime configuration.
    """

    def __init__(self, db: Database, settings: Optional[Settings] = None) -> None:
        self._db = db
        self._cfg = settings or get_settings()

    def transform(
        self,
        ctp_id: str,
        target_capacity_mbps: float,
        output_dir: str,
        users_root: str,
        throughput_threshold_mbps: Optional[float] = None,
    ) -> Tuple[CrossTrafficProfile, Path, Path]:
        """Transform a CTP to the target capacity and produce merged PCAPs.

        Args:
            ctp_id: ID of the CTP to transform.
            target_capacity_mbps: Desired mean throughput after scaling (Mbps).
            output_dir: Root directory for the output PCAP files.
            users_root: Root of the per-user PCAP directory produced by Step 1.
                Used to locate per-user window PCAPs.
            throughput_threshold_mbps: If provided, packets in intervals
                exceeding this rate are dropped (burst trimming).

        Returns:
            Tuple of ``(transformed_ctp, download_pcap_path, upload_pcap_path)``.

        Raises:
            ValueError: If the CTP is not found or has zero intensity.
        """
        # ---- Load original CTP ----
        original = self._db.get_ctp(ctp_id)
        if original is None:
            raise ValueError(f"CTP '{ctp_id}' not found in corpus.")

        original_mbps = original.intensity.mean_mbps
        if original_mbps <= 0:
            raise ValueError(f"CTP '{ctp_id}' has zero intensity; cannot compute scale factor.")

        scale = target_capacity_mbps / original_mbps
        logger.info(
            "Transforming CTP '%s': %.2f Mbps → %.2f Mbps (scale=%.4f)",
            ctp_id,
            original_mbps,
            target_capacity_mbps,
            scale,
        )

        # ---- Resolve leaf users ----
        leaf_ctps = self._db.get_leaf_ctps_for_subnet(
            original.dataset_name, original.subnet, original.window_index
        )
        if not leaf_ctps:
            raise ValueError(
                f"No /32 leaf CTPs found for subnet '{original.subnet}' "
                f"window {original.window_index} in dataset '{original.dataset_name}'."
            )

        leaf_ips = [str(c.subnet).split("/")[0] for c in leaf_ctps]
        logger.debug("Found %d leaf IP(s) for subnet '%s'.", len(leaf_ips), original.subnet)

        # ---- Prepare output directories ----
        dataset_out = Path(output_dir) / original.dataset_name
        downlink_dir = dataset_out / "downlink"
        uplink_dir = dataset_out / "uplink"
        downlink_dir.mkdir(parents=True, exist_ok=True)
        uplink_dir.mkdir(parents=True, exist_ok=True)

        safe_id = ctp_id.replace("/", "_").replace(":", "-")

        # ---- Merge per-user window PCAPs ----
        download_pcap = downlink_dir / f"{safe_id}_download.pcap"
        upload_pcap = uplink_dir / f"{safe_id}_upload.pcap"

        self._merge_user_pcaps(
            leaf_ips=leaf_ips,
            window_index=original.window_index,
            users_root=Path(users_root),
            output_path=download_pcap,
            direction="download",
        )
        self._merge_user_pcaps(
            leaf_ips=leaf_ips,
            window_index=original.window_index,
            users_root=Path(users_root),
            output_path=upload_pcap,
            direction="upload",
        )

        # ---- Reorder packets ----
        for pcap in (download_pcap, upload_pcap):
            if pcap.exists():
                _reorder_single_pcap(pcap)

        # ---- Pad packets to IP header length ----
        for pcap in (download_pcap, upload_pcap):
            if pcap.exists():
                temp = pcap.with_suffix(".pad_tmp.pcap")
                pad_pcap_frames(str(pcap), str(temp))

        # ---- Burst trimming (optional) ----
        if throughput_threshold_mbps is not None:
            threshold_bytes = int(
                throughput_threshold_mbps * 1_000_000 / 8 * _DEFAULT_TRIM_INTERVAL_SEC
            )
            for pcap in (download_pcap, upload_pcap):
                if pcap.exists():
                    trimmed = pcap.with_suffix(".trimmed.pcap")
                    trim_pcap_by_rate(
                        str(pcap),
                        str(trimmed),
                        threshold_bytes=threshold_bytes,
                        interval_sec=_DEFAULT_TRIM_INTERVAL_SEC,
                    )
                    trimmed.rename(pcap)  # replace original with trimmed version

        # ---- Build transformed CTP descriptor ----
        transformed_id = f"ctp-transform-{safe_id}-{target_capacity_mbps:.0f}mbps"
        transformed = CrossTrafficProfile(
            ctp_id=transformed_id,
            dataset_name=original.dataset_name,
            subnet=original.subnet,
            window_index=original.window_index,
            extracted_from=original.extracted_from,
            duration_seconds=original.duration_seconds,
            # Scale timeseries by the amplitude factor
            upload_timeseries=[v * scale for v in original.upload_timeseries],
            download_timeseries=[v * scale for v in original.download_timeseries],
            # Scale intensity
            intensity=CTPIntensity(
                mean_bps=original.intensity.mean_bps * scale,
                peak_bps=original.intensity.peak_bps * scale,
                mean_pps=original.intensity.mean_pps * scale,
                peak_pps=original.intensity.peak_pps * scale,
            ),
            # Preserve temporal shape and structure
            burstiness=original.burstiness,
            temporal_correlation=original.temporal_correlation,
            structure=original.structure,
        )
        self._db.upsert_ctp(transformed)

        logger.info(
            "Transform complete: '%s' → '%s'  download=%s  upload=%s",
            ctp_id,
            transformed_id,
            download_pcap,
            upload_pcap,
        )
        return transformed, download_pcap, upload_pcap

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _merge_user_pcaps(
        self,
        leaf_ips: List[str],
        window_index: int,
        users_root: Path,
        output_path: Path,
        direction: str,
    ) -> None:
        """Collect and merge per-user window PCAPs for one direction.

        Gathers the PCAP at
        ``<users_root>/<ip>/<direction>/windows/**/window_XXXX.pcap``
        for each IP and merges them into *output_path* using ``joincap``.

        Args:
            leaf_ips: List of /32 IP address strings.
            window_index: Window index (1-based).
            users_root: Root of the per-user directory tree.
            output_path: Destination merged PCAP path.
            direction: ``'upload'`` or ``'download'``.
        """
        pcap_files: List[str] = []
        for ip in leaf_ips:
            pattern = f"window_{window_index:04d}.pcap"
            base = users_root / ip / direction / "windows"
            matches = sorted(base.rglob(pattern))
            pcap_files.extend(str(m) for m in matches)

        if not pcap_files:
            logger.warning(
                "No %s PCAP files for window %d found; skipping merge.",
                direction,
                window_index,
            )
            return

        cmd = ["joincap", "-w", str(output_path)] + pcap_files
        logger.debug("Merging %d %s PCAP(s) into '%s'", len(pcap_files), direction, output_path)
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            logger.error("joincap failed: %s", exc.stderr.decode(errors="replace"))
            raise


def _reorder_single_pcap(pcap_path: Path) -> None:
    """Reorder packets in a single PCAP file using ``reordercap``.

    Writes to a temporary file then replaces the original.

    Args:
        pcap_path: Path to the PCAP to reorder (modified in-place).
    """
    tmp = pcap_path.with_suffix(".reorder_tmp.pcap")
    try:
        subprocess.run(
            ["reordercap", str(pcap_path), str(tmp)],
            check=True,
            capture_output=True,
        )
        tmp.rename(pcap_path)
    except subprocess.CalledProcessError as exc:
        logger.error(
            "reordercap failed for '%s': %s", pcap_path, exc.stderr.decode(errors="replace")
        )
        if tmp.exists():
            tmp.unlink()
        raise
