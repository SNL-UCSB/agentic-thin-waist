"""
ctp.py — Core CTP dataclasses.

A **Cross-Traffic Profile (CTP)** is a reusable representation of dynamic
congestion pressure at a network bottleneck.  It encodes the temporal
structure of aggregate demand (intensity, burstiness, heterogeneity, temporal
correlation) without binding to particular paths, applications, or users.

Each CTP corresponds to one *subnet* at one *time window* in a captured trace.
The full corpus is stored in PostgreSQL; these dataclasses are the in-process
representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class CTPIntensity:
    """Traffic intensity metrics for a CTP.

    All rates are computed over the timeseries produced in Step 3.

    Attributes:
        mean_pps: Mean packet rate over the window (packets/s).
        mean_bps: Mean bit rate over the window (bits/s).
        peak_pps: Peak (per-bin maximum) packet rate (packets/s).
        peak_bps: Peak bit rate (bits/s).
        mean_mbps: Mean bit rate in Mbps (derived from mean_bps).
    """

    mean_pps: float
    mean_bps: float
    peak_pps: float
    peak_bps: float

    @property
    def mean_mbps(self) -> float:
        """Mean throughput in Mbps."""
        return self.mean_bps / 1_000_000


@dataclass
class CTPBurstiness:
    """Burstiness metrics for a CTP.

    Multiple complementary measures capture different aspects of traffic
    variability at the 100 ms bin timescale.

    Attributes:
        peak_to_mean_ratio: PMR = max(timeseries) / mean(timeseries).
            Measures the worst-case spike relative to average load.
        coefficient_of_variation: CoV = std / mean.
            Normalised dispersion; independent of absolute rate.
        percentile_95_to_mean: P95/mean ratio.
            Robust version of PMR that is less sensitive to single outliers.
        on_periods: Number of contiguous ON (non-zero traffic) runs.
        off_periods: Number of contiguous OFF (zero traffic) runs.
    """

    peak_to_mean_ratio: float
    coefficient_of_variation: float
    percentile_95_to_mean: float
    on_periods: int
    off_periods: int


@dataclass
class CTPTemporalCorrelation:
    """Lag-k autocorrelation of the traffic timeseries.

    Autocorrelation measures how strongly a bin's value is predicted by
    values *k* bins earlier.  High lag-1 autocorrelation indicates smooth,
    slowly-varying traffic; low values indicate bursty or random arrivals.

    Attributes:
        lag_1: Autocorrelation at lag 1 (adjacent bins).
        lag_5: Autocorrelation at lag 5 (~500 ms with 100 ms bins).
        lag_10: Autocorrelation at lag 10 (~1 s).
        lag_60: Autocorrelation at lag 60 (~6 s).  Optional; ``None`` if the
            timeseries is shorter than 61 bins.
    """

    lag_1: float
    lag_5: float
    lag_10: float
    lag_60: Optional[float] = None


@dataclass
class CTPStructure:
    """Structural properties of the contributor composition.

    Attributes:
        contributor_count: Number of unique internal /32 leaf hosts.
        unique_source_ips: Distinct source IP addresses.
        unique_dest_ips: Distinct destination IP addresses.
        upload_download_ratio: Asymmetry = upload_bytes / download_bytes.
            Values > 1 indicate more upload than download.  ``-1`` when
            download bytes are zero.
        prefix_diversity: Shannon entropy of the contributor prefix
            distribution, normalised to [0, 1].  Higher values indicate
            more spatially diverse traffic.
    """

    contributor_count: int
    unique_source_ips: int
    unique_dest_ips: int
    upload_download_ratio: float
    prefix_diversity: float


@dataclass
class CrossTrafficProfile:
    """Complete CTP representation stored in the corpus.

    A CTP uniquely identifies one subnet at one time-window index within a
    named dataset.  The raw timeseries and all statistical descriptors are
    stored alongside the CTP for efficient multi-dimensional querying.

    Attributes:
        ctp_id: Globally unique identifier (e.g. ``ctp-<dataset>-<subnet>-<window>``).
        dataset_name: Human-readable name for the capture dataset.
        subnet: CIDR notation of the represented subnet, e.g. ``169.231.0.0/16``.
        window_index: Zero-based time-window index within the dataset.
        extracted_from: Source PCAP filename(s).
        start_time: Wall-clock start of this time window (may be ``None`` if
            timestamps were not available).
        duration_seconds: Length of the time window in seconds.
        upload_timeseries: Byte counts per bin for outbound (upload) traffic.
        download_timeseries: Byte counts per bin for inbound (download) traffic.
        intensity: Intensity metrics.
        burstiness: Burstiness metrics.
        temporal_correlation: Autocorrelation at multiple lags.
        structure: Contributor composition metrics.
        created_at: Timestamp when this CTP was inserted into the corpus.
    """

    ctp_id: str
    dataset_name: str
    subnet: str
    window_index: int
    extracted_from: str
    duration_seconds: int
    upload_timeseries: List[float]
    download_timeseries: List[float]
    intensity: CTPIntensity
    burstiness: CTPBurstiness
    temporal_correlation: CTPTemporalCorrelation
    structure: CTPStructure
    start_time: Optional[datetime] = None
    created_at: Optional[datetime] = None

    @property
    def timeseries_length(self) -> int:
        """Number of bins in the timeseries."""
        return len(self.download_timeseries)

    def to_db_dict(self) -> dict:
        """Serialise to a flat dict suitable for PostgreSQL insertion.

        JSON-serialisable; timeseries are stored as Python lists and will be
        cast to ``FLOAT8[]`` by psycopg2.

        Returns:
            Dictionary with keys matching ``ctp_nodes`` table columns.
        """
        return {
            "ctp_id": self.ctp_id,
            "dataset_name": self.dataset_name,
            "subnet": self.subnet,
            "window_index": self.window_index,
            "extracted_from": self.extracted_from,
            "start_time": self.start_time,
            "duration_seconds": self.duration_seconds,
            "upload_timeseries": self.upload_timeseries,
            "download_timeseries": self.download_timeseries,
            "contributor_count": self.structure.contributor_count,
            "intensity": {
                "mean_pps": self.intensity.mean_pps,
                "mean_bps": self.intensity.mean_bps,
                "mean_mbps": self.intensity.mean_mbps,
                "peak_pps": self.intensity.peak_pps,
                "peak_bps": self.intensity.peak_bps,
            },
            "burstiness": {
                "peak_to_mean_ratio": self.burstiness.peak_to_mean_ratio,
                "coefficient_of_variation": self.burstiness.coefficient_of_variation,
                "percentile_95_to_mean": self.burstiness.percentile_95_to_mean,
                "on_periods": self.burstiness.on_periods,
                "off_periods": self.burstiness.off_periods,
            },
            "temporal_correlation": {
                "lag_1": self.temporal_correlation.lag_1,
                "lag_5": self.temporal_correlation.lag_5,
                "lag_10": self.temporal_correlation.lag_10,
                "lag_60": self.temporal_correlation.lag_60,
            },
            "structure": {
                "contributor_count": self.structure.contributor_count,
                "unique_source_ips": self.structure.unique_source_ips,
                "unique_dest_ips": self.structure.unique_dest_ips,
                "upload_download_ratio": self.structure.upload_download_ratio,
                "prefix_diversity": self.structure.prefix_diversity,
            },
            "created_at": self.created_at,
        }
