"""
merge.py — Merge operation: combine CTPs by concatenating windows or composing with weights.

Two merge modes are supported:

**Window concatenation** (``merge_windows``)
    Concatenate consecutive time-window CTPs for the same subnet into a longer
    profile.  The timeseries arrays are concatenated and all metrics are
    recomputed over the combined series.  This produces a CTP spanning
    ``N × window_duration`` seconds.

    Example: 4 × 30-second windows → one 2-minute profile.

**Weighted composition** (``merge_weighted``)
    Linearly combine the timeseries of multiple CTPs using scalar weights.
    The resulting timeseries is the element-wise weighted sum (CTPs must share
    the same length).  Metrics are recomputed on the combined series.

    Example: mix two CTPs at 70 % / 30 % to create a synthetic workload.

In both cases the merged CTP is stored in the database and returned.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import numpy as np

from app.config import Settings, get_settings
from app.database.postgres import Database
from app.models.ctp import (
    CTPBurstiness,
    CTPIntensity,
    CTPStructure,
    CTPTemporalCorrelation,
    CrossTrafficProfile,
)
from app.operations.metrics import compute_all_metrics

logger = logging.getLogger(__name__)


class CTPMerger:
    """Combine CTPs by window concatenation or weighted composition.

    Args:
        db: Initialised :class:`~app.database.postgres.Database` instance.
        settings: Runtime configuration.
    """

    def __init__(self, db: Database, settings: Optional[Settings] = None) -> None:
        self._db = db
        self._cfg = settings or get_settings()

    # ------------------------------------------------------------------ #
    # Window concatenation
    # ------------------------------------------------------------------ #

    def merge_windows(
        self,
        ctp_ids: List[str],
        new_ctp_id: Optional[str] = None,
    ) -> CrossTrafficProfile:
        """Concatenate consecutive windows into a single longer CTP.

        All source CTPs must belong to the same dataset and subnet.  Their
        timeseries are concatenated in the order provided by *ctp_ids*.

        Args:
            ctp_ids: Ordered list of CTP IDs to concatenate.
            new_ctp_id: Override the auto-generated ID for the merged CTP.

        Returns:
            The merged :class:`~app.models.ctp.CrossTrafficProfile` (also stored in DB).

        Raises:
            ValueError: If any CTP is not found or if dataset/subnet mismatch.
        """
        ctps = self._load_and_validate(ctp_ids, require_same_length=False)

        upload_ts = np.concatenate([np.array(c.upload_timeseries) for c in ctps])
        download_ts = np.concatenate([np.array(c.download_timeseries) for c in ctps])

        return self._build_merged_ctp(
            ctps=ctps,
            upload_ts=upload_ts,
            download_ts=download_ts,
            new_ctp_id=new_ctp_id,
            merge_mode="windows",
            weights=[1.0 / len(ctps)] * len(ctps),
        )

    # ------------------------------------------------------------------ #
    # Weighted composition
    # ------------------------------------------------------------------ #

    def merge_weighted(
        self,
        ctp_ids: List[str],
        weights: Optional[List[float]] = None,
        new_ctp_id: Optional[str] = None,
    ) -> CrossTrafficProfile:
        """Compose multiple CTPs with scalar weights.

        Each CTP's timeseries is multiplied by its weight and the results are
        summed element-wise.  All CTPs must have the same timeseries length.

        Args:
            ctp_ids: List of CTP IDs to compose.
            weights: Per-CTP weights.  Must sum to 1.0.  Equal weights are
                used when ``None``.
            new_ctp_id: Override the auto-generated merged CTP ID.

        Returns:
            The merged :class:`~app.models.ctp.CrossTrafficProfile`.

        Raises:
            ValueError: If CTPs are not found, lengths differ, or weights are invalid.
        """
        ctps = self._load_and_validate(ctp_ids, require_same_length=True)

        n = len(ctps)
        if weights is None:
            weights = [1.0 / n] * n
        elif len(weights) != n:
            raise ValueError(f"len(weights)={len(weights)} must equal len(ctp_ids)={n}.")

        total_weight = sum(weights)
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(f"Weights must sum to 1.0; got {total_weight:.6f}.")

        upload_ts = sum(w * np.array(c.upload_timeseries) for w, c in zip(weights, ctps))
        download_ts = sum(w * np.array(c.download_timeseries) for w, c in zip(weights, ctps))

        return self._build_merged_ctp(
            ctps=ctps,
            upload_ts=upload_ts,
            download_ts=download_ts,
            new_ctp_id=new_ctp_id,
            merge_mode="weighted",
            weights=weights,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _load_and_validate(
        self,
        ctp_ids: List[str],
        require_same_length: bool,
    ) -> List[CrossTrafficProfile]:
        """Load CTPs from the DB and validate dataset/subnet consistency.

        Args:
            ctp_ids: CTP identifiers to load.
            require_same_length: When ``True``, enforce that all timeseries
                have the same number of bins.

        Returns:
            Ordered list of loaded CTPs.

        Raises:
            ValueError: If any CTP is missing or fails validation.
        """
        ctps: List[CrossTrafficProfile] = []
        for cid in ctp_ids:
            ctp = self._db.get_ctp(cid)
            if ctp is None:
                raise ValueError(f"CTP '{cid}' not found in corpus.")
            ctps.append(ctp)

        if not ctps:
            raise ValueError("No CTPs provided for merge.")

        # Validate same dataset and subnet
        dataset = ctps[0].dataset_name
        subnet = ctps[0].subnet
        for ctp in ctps[1:]:
            if ctp.dataset_name != dataset:
                raise ValueError(
                    f"All CTPs must share the same dataset; "
                    f"got '{dataset}' and '{ctp.dataset_name}'."
                )
            if ctp.subnet != subnet:
                raise ValueError(
                    f"All CTPs must share the same subnet; " f"got '{subnet}' and '{ctp.subnet}'."
                )

        if require_same_length:
            length = len(ctps[0].download_timeseries)
            for ctp in ctps[1:]:
                if len(ctp.download_timeseries) != length:
                    raise ValueError(
                        f"All CTPs must have the same timeseries length for weighted "
                        f"merge; CTP '{ctps[0].ctp_id}' has {length} bins but "
                        f"'{ctp.ctp_id}' has {len(ctp.download_timeseries)} bins."
                    )
        return ctps

    def _build_merged_ctp(
        self,
        ctps: List[CrossTrafficProfile],
        upload_ts: np.ndarray,
        download_ts: np.ndarray,
        new_ctp_id: Optional[str],
        merge_mode: str,
        weights: List[float],
    ) -> CrossTrafficProfile:
        """Compute metrics on the merged timeseries and store the result.

        Args:
            ctps: Source CTPs (for metadata inheritance).
            upload_ts: Merged upload timeseries array.
            download_ts: Merged download timeseries array.
            new_ctp_id: Override auto-generated ID (or ``None``).
            merge_mode: ``'windows'`` or ``'weighted'``.
            weights: List of weights applied.

        Returns:
            Stored merged :class:`~app.models.ctp.CrossTrafficProfile`.
        """
        bin_sec = self._cfg.burst_interval_ms / 1000.0
        intensity, burstiness, correlation, _ = compute_all_metrics(
            upload_ts=upload_ts,
            download_ts=download_ts,
            bin_width_sec=bin_sec,
        )

        # Aggregate contributor IPs across all source CTPs
        all_ips = list({str(c.subnet).split("/")[0] for c in ctps})
        contributor_count = sum(c.structure.contributor_count for c in ctps)
        total_upload = float(np.sum(upload_ts))
        total_download = float(np.sum(download_ts))

        structure = CTPStructure(
            contributor_count=contributor_count,
            unique_source_ips=len(all_ips),
            unique_dest_ips=len(all_ips),
            upload_download_ratio=(total_upload / total_download if total_download > 0 else -1.0),
            prefix_diversity=ctps[0].structure.prefix_diversity,
        )

        first = ctps[0]
        if new_ctp_id is None:
            ts_now = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
            new_ctp_id = (
                f"ctp-merge-{merge_mode}-{first.dataset_name}-"
                f"{first.subnet.replace('/', '_')}-{ts_now}"
            )

        merged = CrossTrafficProfile(
            ctp_id=new_ctp_id,
            dataset_name=first.dataset_name,
            subnet=first.subnet,
            window_index=first.window_index,
            extracted_from=",".join(c.ctp_id for c in ctps),
            duration_seconds=sum(c.duration_seconds for c in ctps),
            upload_timeseries=upload_ts.tolist(),
            download_timeseries=download_ts.tolist(),
            intensity=intensity,
            burstiness=burstiness,
            temporal_correlation=correlation,
            structure=structure,
        )

        self._db.upsert_ctp(merged)
        logger.info(
            "Merged %d CTP(s) [%s] → '%s'  intensity=%.2f Mbps",
            len(ctps),
            merge_mode,
            new_ctp_id,
            merged.intensity.mean_mbps,
        )
        return merged
