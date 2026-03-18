"""
metrics.py — Statistical descriptor computation for CTP timeseries.

All metric functions operate on 1-D NumPy arrays where each element is the
total byte count in one *burst interval* bin (default 100 ms).

Metric catalogue
~~~~~~~~~~~~~~~~

**Intensity**
    - ``mean_bps``: mean byte rate scaled to bits/s.
    - ``mean_pps``: estimated mean packet rate (bytes ÷ avg_packet_size).
    - ``peak_bps`` / ``peak_pps``: per-bin maximum.

**Burstiness**
    - ``peak_to_mean_ratio`` (PMR): ``max / mean``.
    - ``coefficient_of_variation`` (CoV): ``std / mean``.
    - ``percentile_95_to_mean``: ``P95 / mean``.
    - ``on_periods`` / ``off_periods``: count of contiguous non-zero / zero runs.

**Temporal correlation**
    - Lag-*k* Pearson autocorrelation at lags 1, 5, 10, 60.

**Structure**
    - ``prefix_diversity``: normalised Shannon entropy over /24 prefix distribution
      of contributor IPs.

All functions return ``0.0`` (or ``0``) when the denominator would be zero
(e.g. zero-traffic window).
"""

from __future__ import annotations

import logging
import math
from typing import List, Optional, Set

import numpy as np

from app.models.ctp import (
    CTPBurstiness,
    CTPIntensity,
    CTPStructure,
    CTPTemporalCorrelation,
)

logger = logging.getLogger(__name__)

# Assumed average IP packet size when PPS must be estimated from byte series.
_DEFAULT_AVG_PACKET_BYTES: float = 500.0


# ---------------------------------------------------------------------------
# Intensity
# ---------------------------------------------------------------------------


def compute_intensity(
    timeseries: np.ndarray,
    bin_width_sec: float,
    avg_packet_bytes: float = _DEFAULT_AVG_PACKET_BYTES,
) -> CTPIntensity:
    """Compute traffic intensity metrics from a byte-count timeseries.

    Each element of *timeseries* is the total **bytes** transferred in one
    bin of width *bin_width_sec* seconds.  Rates are computed by dividing by
    the bin width, then converting bytes → bits where needed.

    Args:
        timeseries: 1-D array of per-bin byte counts.
        bin_width_sec: Duration of each bin in seconds (e.g. 0.1 for 100 ms).
        avg_packet_bytes: Estimated average IP packet size; used to derive
            approximate PPS from the byte series.

    Returns:
        :class:`~app.models.ctp.CTPIntensity` with mean and peak rates.
    """
    if timeseries.size == 0 or np.sum(timeseries) == 0:
        return CTPIntensity(mean_pps=0.0, mean_bps=0.0, peak_pps=0.0, peak_bps=0.0)

    # Byte-rate per bin → divide by bin width in seconds
    byte_rates = timeseries / bin_width_sec  # bytes/s
    bit_rates = byte_rates * 8  # bits/s
    pkt_rates = byte_rates / max(avg_packet_bytes, 1.0)  # packets/s

    return CTPIntensity(
        mean_bps=float(np.mean(bit_rates)),
        peak_bps=float(np.max(bit_rates)),
        mean_pps=float(np.mean(pkt_rates)),
        peak_pps=float(np.max(pkt_rates)),
    )


# ---------------------------------------------------------------------------
# Burstiness
# ---------------------------------------------------------------------------


def compute_burstiness(timeseries: np.ndarray) -> CTPBurstiness:
    """Compute burstiness metrics for a byte-count timeseries.

    Args:
        timeseries: 1-D array of per-bin byte counts.

    Returns:
        :class:`~app.models.ctp.CTPBurstiness` with PMR, CoV, P95/mean, and
        on/off period counts.
    """
    if timeseries.size == 0 or np.sum(timeseries) == 0:
        return CTPBurstiness(
            peak_to_mean_ratio=0.0,
            coefficient_of_variation=0.0,
            percentile_95_to_mean=0.0,
            on_periods=0,
            off_periods=0,
        )

    ts_mean = float(np.mean(timeseries))

    pmr = float(np.max(timeseries)) / ts_mean if ts_mean > 0 else 0.0
    cov = float(np.std(timeseries)) / ts_mean if ts_mean > 0 else 0.0
    p95 = float(np.percentile(timeseries, 95)) / ts_mean if ts_mean > 0 else 0.0

    on_periods, off_periods = _count_on_off_periods(timeseries)

    return CTPBurstiness(
        peak_to_mean_ratio=pmr,
        coefficient_of_variation=cov,
        percentile_95_to_mean=p95,
        on_periods=on_periods,
        off_periods=off_periods,
    )


def _count_on_off_periods(timeseries: np.ndarray) -> tuple[int, int]:
    """Count contiguous ON (non-zero) and OFF (zero) runs.

    Args:
        timeseries: 1-D array of per-bin values.

    Returns:
        Tuple ``(on_periods, off_periods)``.
    """
    if timeseries.size == 0:
        return 0, 0

    is_on = timeseries > 0
    on_periods = 0
    off_periods = 0
    prev = None

    for val in is_on:
        if prev is None:
            if val:
                on_periods += 1
            else:
                off_periods += 1
        else:
            if val and not prev:
                on_periods += 1
            elif not val and prev:
                off_periods += 1
        prev = val

    return on_periods, off_periods


# ---------------------------------------------------------------------------
# Temporal correlation
# ---------------------------------------------------------------------------


def compute_temporal_correlation(timeseries: np.ndarray) -> CTPTemporalCorrelation:
    """Compute Pearson autocorrelation at lags 1, 5, 10, and 60.

    Autocorrelation at lag *k* is the Pearson correlation between
    ``timeseries[:-k]`` and ``timeseries[k:]``.  Returns 0.0 for any lag
    that cannot be computed (timeseries too short, zero variance).

    Args:
        timeseries: 1-D array of per-bin byte counts.

    Returns:
        :class:`~app.models.ctp.CTPTemporalCorrelation` with lag values.
    """
    return CTPTemporalCorrelation(
        lag_1=_autocorr(timeseries, 1),
        lag_5=_autocorr(timeseries, 5),
        lag_10=_autocorr(timeseries, 10),
        lag_60=_autocorr(timeseries, 60) if len(timeseries) > 61 else None,
    )


def _autocorr(timeseries: np.ndarray, lag: int) -> float:
    """Pearson autocorrelation at *lag* bins.

    Args:
        timeseries: 1-D array.
        lag: Number of bins to shift.

    Returns:
        Float in [-1, 1], or 0.0 if the computation is undefined.
    """
    if len(timeseries) <= lag:
        return 0.0
    x = timeseries[:-lag].astype(float)
    y = timeseries[lag:].astype(float)
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    try:
        corr = float(np.corrcoef(x, y)[0, 1])
        return 0.0 if math.isnan(corr) else corr
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def compute_structure(
    contributor_ips: List[str],
    upload_bytes: float,
    download_bytes: float,
) -> CTPStructure:
    """Compute contributor structure metrics.

    Args:
        contributor_ips: List of internal /32 IP address strings that
            contribute to this CTP node.
        upload_bytes: Total upload byte count for the node.
        download_bytes: Total download byte count for the node.

    Returns:
        :class:`~app.models.ctp.CTPStructure`.
    """
    contributor_count = len(contributor_ips)
    unique_src = contributor_count  # /32 hosts are both src and dst
    unique_dst = contributor_count

    asymmetry = (upload_bytes / download_bytes) if download_bytes > 0 else -1.0
    diversity = _prefix_diversity(contributor_ips)

    return CTPStructure(
        contributor_count=contributor_count,
        unique_source_ips=unique_src,
        unique_dest_ips=unique_dst,
        upload_download_ratio=asymmetry,
        prefix_diversity=diversity,
    )


def _prefix_diversity(ips: List[str], prefix_octets: int = 3) -> float:
    """Normalised Shannon entropy of the /24 prefix distribution of *ips*.

    Groups IPs by their first *prefix_octets* octets (i.e. /24 by default)
    and computes the entropy of that distribution, normalised by log2(N)
    so the result is in [0, 1].

    Args:
        ips: List of dotted-decimal IPv4 strings.
        prefix_octets: Number of octets to use as the prefix group key.

    Returns:
        Float in [0, 1].  Returns 0.0 for empty or singleton lists.
    """
    if len(ips) <= 1:
        return 0.0

    # Build prefix groups
    prefix_counts: dict[str, int] = {}
    for ip in ips:
        parts = ip.split(".")
        prefix = ".".join(parts[:prefix_octets])
        prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

    n = len(ips)
    entropy = -sum(
        (count / n) * math.log2(count / n)
        for count in prefix_counts.values()
        if count > 0
    )
    max_entropy = math.log2(len(prefix_counts)) if len(prefix_counts) > 1 else 1.0
    return entropy / max_entropy if max_entropy > 0 else 0.0


# ---------------------------------------------------------------------------
# Combined descriptor computation from a timeseries array
# ---------------------------------------------------------------------------


def compute_all_metrics(
    upload_ts: np.ndarray,
    download_ts: np.ndarray,
    bin_width_sec: float,
    contributor_ips: Optional[List[str]] = None,
) -> tuple[CTPIntensity, CTPBurstiness, CTPTemporalCorrelation, CTPStructure]:
    """Compute all four descriptor groups for a single CTP node.

    Uses the **combined** (upload + download) timeseries for intensity,
    burstiness, and temporal correlation metrics, to capture the aggregate
    congestion pressure applied at the bottleneck.

    Args:
        upload_ts: Per-bin upload byte counts.
        download_ts: Per-bin download byte counts.
        bin_width_sec: Bin width in seconds.
        contributor_ips: List of /32 IP strings for structure metrics.
            Defaults to empty list when not provided.

    Returns:
        Tuple of (intensity, burstiness, temporal_correlation, structure).
    """
    combined_ts = upload_ts + download_ts
    contributor_ips = contributor_ips or []

    intensity = compute_intensity(combined_ts, bin_width_sec)
    burstiness = compute_burstiness(combined_ts)
    correlation = compute_temporal_correlation(combined_ts)

    upload_bytes = float(np.sum(upload_ts))
    download_bytes = float(np.sum(download_ts))
    structure = compute_structure(contributor_ips, upload_bytes, download_bytes)

    return intensity, burstiness, correlation, structure
