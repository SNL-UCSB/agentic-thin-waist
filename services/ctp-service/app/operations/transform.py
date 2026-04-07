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
import struct
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.config import Settings, get_settings
from app.database.postgres import Database
from app.models.ctp import CrossTrafficProfile
from app.operations.extract import build_timeseries_from_window
from app.operations.metrics import compute_all_metrics
from app.pcap_utils import (
    clip_pcap_to_window,
    merge_pcaps_by_index,
    pad_pcap_frames,
    _reorder_single_pcap,
    trim_pcap_by_rate,
)

logger = logging.getLogger(__name__)

# Valid PCAP global header (little-endian, Ethernet link type).
# Written to produce an empty-but-valid PCAP when a direction has no traffic.
_PCAP_GLOBAL_HEADER: bytes = struct.pack(
    "<IHHiIII",
    0xA1B2C3D4,  # magic number
    2,
    4,  # version major/minor
    0,  # UTC offset
    0,  # timestamp accuracy
    65535,  # snapshot length
    1,  # link type: Ethernet
)


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
        output_dir: str,
        users_root: str,
        throughput_threshold_mbps: float,
    ) -> Tuple[CrossTrafficProfile, Path, Path]:
        """Transform a CTP to the target capacity and produce merged PCAPs.

        Args:
            ctp_id: ID of the CTP to transform.
            output_dir: Root directory for the output PCAP files.
            users_root: Root of the per-user PCAP directory produced by Step 1.
                Used to locate per-user window PCAPs.
            throughput_threshold_mbps: packets in intervals
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
        logger.debug(
            "Found %d leaf IP(s) for subnet '%s'.", len(leaf_ips), original.subnet
        )

        # ---- Prepare output directories ----
        dataset_out = Path(output_dir) / f"{original.dataset_name}_transformed"
        downlink_dir = dataset_out / "downlink"
        uplink_dir = dataset_out / "uplink"
        downlink_dir.mkdir(parents=True, exist_ok=True)
        uplink_dir.mkdir(parents=True, exist_ok=True)

        safe_id = ctp_id.replace("/", "_").replace(":", "-")

        # ---- Merge per-user window PCAPs ----
        download_pcap = (
            downlink_dir / f"{safe_id}_{throughput_threshold_mbps:.0f}mbps.pcap"
        )
        upload_pcap = uplink_dir / f"{safe_id}_{throughput_threshold_mbps:.0f}mbps.pcap"

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

        # ---- Clip to window duration ----
        # The per-user window PCAPs can span more than window_sec seconds
        # (e.g. the full capture).  Clip here so the output PCAP duration
        # matches the CTP timeseries and measured throughput is consistent.
        for pcap in (download_pcap, upload_pcap):
            if pcap.exists():
                clipped = pcap.with_suffix(".clipped.pcap")
                clip_pcap_to_window(str(pcap), str(clipped), window_sec=original.duration_seconds)
                clipped.rename(pcap)

        # ---- Reorder packets ----
        for pcap in (download_pcap, upload_pcap):
            if pcap.exists():
                _reorder_single_pcap(pcap)

        # ---- Pad packets to IP header length ----
        for pcap in (download_pcap, upload_pcap):
            if pcap.exists():
                temp = pcap.with_suffix(".pad_tmp.pcap")
                pad_pcap_frames(str(pcap), str(temp))

        bin_ms = self._cfg.burst_interval_ms
        bin_sec = bin_ms / 1000.0
        window_sec = original.duration_seconds

        # ---- Burst trimming  ----
        if throughput_threshold_mbps is not None:
            threshold_bytes = int(throughput_threshold_mbps * 1_000_000 / 8 * bin_sec)
            for pcap in (download_pcap, upload_pcap):
                if pcap.exists():
                    trimmed = pcap.with_suffix(".trimmed.pcap")
                    trim_pcap_by_rate(
                        str(pcap),
                        str(trimmed),
                        threshold_bytes=threshold_bytes,
                        interval_sec=bin_sec,
                    )
                    trimmed.rename(pcap)  # replace original with trimmed version

        # ---- Recalculate timeseries and metrics from the trimmed PCAPs ----

        new_download_ts = build_timeseries_from_window(
            download_pcap, bin_width_ms=bin_ms, window_sec=window_sec
        )
        new_upload_ts = build_timeseries_from_window(
            upload_pcap, bin_width_ms=bin_ms, window_sec=window_sec
        )

        (
            new_intensity,
            new_burstiness,
            new_correlation,
            new_structure,
        ) = compute_all_metrics(
            upload_ts=new_upload_ts,
            download_ts=new_download_ts,
            bin_width_sec=bin_sec,
            contributor_ips=leaf_ips,
        )

        # ---- Build transformed CTP descriptor ----
        transformed_id = f"ctp-transform-{safe_id}-{throughput_threshold_mbps:.0f}mbps"
        transformed = CrossTrafficProfile(
            ctp_id=transformed_id,
            dataset_name=original.dataset_name,
            subnet=original.subnet,
            window_index=original.window_index,
            extracted_from=original.extracted_from,
            duration_seconds=original.duration_seconds,
            upload_timeseries=new_upload_ts.tolist(),
            download_timeseries=new_download_ts.tolist(),
            intensity=new_intensity,
            burstiness=new_burstiness,
            temporal_correlation=new_correlation,
            structure=new_structure,
            # Transform metadata
            is_transformed=True,
            throughput_threshold_mbps=throughput_threshold_mbps,
            download_pcap=str(download_pcap),
            upload_pcap=str(upload_pcap),
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
                "No %s PCAP files for window %d found; writing empty PCAP.",
                direction,
                window_index,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(_PCAP_GLOBAL_HEADER)
            return

        cmd = ["joincap", "-w", str(output_path)] + pcap_files
        logger.debug(
            "Merging %d %s PCAP(s) into '%s'", len(pcap_files), direction, output_path
        )
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            logger.error("joincap failed: %s", exc.stderr.decode(errors="replace"))
            raise
