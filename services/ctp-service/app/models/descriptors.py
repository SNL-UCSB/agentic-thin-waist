"""
descriptors.py — Request/response Pydantic models for the CTP Service API.

These models are used by FastAPI for automatic request validation, OpenAPI
schema generation, and response serialisation.  They mirror the dataclasses
in ``ctp.py`` but are Pydantic ``BaseModel`` subclasses so FastAPI can
validate incoming JSON and produce typed responses.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Extract operation
# ---------------------------------------------------------------------------


class ExtractRequest(BaseModel):
    """Request body for ``POST /ctps/extract``.

    Attributes:
        pcap_input: Absolute path to a PCAP file or directory of PCAPs.
        output_dir: Root directory for intermediate per-user PCAP files.
        dataset_name: Human-readable label for this capture dataset.
        window_duration_sec: Override the default time-window length.
        burst_interval_ms: Override the default bin width.
        internal_subnets: Override the default UCSB campus prefixes.
        workers: Override the default worker count.
        start_time_epoch: Unix timestamp of the first packet (optional).
            When provided it is stored as the window start time.
    """

    pcap_input: str = Field(..., description="Path to PCAP file or directory.")
    output_dir: str = Field(..., description="Root directory for intermediate files.")
    dataset_name: str = Field(..., description="Human-readable dataset label.")
    window_duration_sec: Optional[int] = Field(None, ge=1)
    burst_interval_ms: Optional[int] = Field(None, ge=1)
    internal_subnets: Optional[List[str]] = None
    workers: Optional[int] = Field(None, ge=1)
    start_time_epoch: Optional[float] = None


class ExtractResponse(BaseModel):
    """Response body for ``POST /ctps/extract``."""

    dataset_name: str
    ctp_count: int
    window_count: int
    user_count: int
    extraction_status: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Select operation
# ---------------------------------------------------------------------------


class SelectQuery(BaseModel):
    """Filter parameters for ``POST /ctps/select``.

    All fields are optional; omitting a field removes that constraint.
    Range fields are ``[min, max]`` inclusive.

    Attributes:
        dataset_name: Restrict to CTPs from a specific dataset.
        subnet_prefix_len: Only return CTPs at this prefix length (e.g. 24
            for /24 nodes).
        intensity_range_mbps: ``[min_mbps, max_mbps]`` inclusive.
        burstiness_pmr_range: ``[min_pmr, max_pmr]`` inclusive.
        burstiness_cov_range: ``[min_cov, max_cov]`` inclusive.
        temporal_correlation_min: Minimum lag-1 autocorrelation.
        contributor_count_min: Minimum number of /32 leaf hosts.
        contributor_count_max: Maximum number of /32 leaf hosts.
        upload_download_ratio_max: Maximum asymmetry ratio.
        window_index_range: ``[start_window, end_window]`` inclusive.
    """

    dataset_name: Optional[str] = None
    subnet_prefix_len: Optional[int] = Field(None, ge=1, le=32)
    intensity_range_mbps: Optional[List[float]] = Field(
        None, min_length=2, max_length=2
    )
    burstiness_pmr_range: Optional[List[float]] = Field(
        None, min_length=2, max_length=2
    )
    burstiness_cov_range: Optional[List[float]] = Field(
        None, min_length=2, max_length=2
    )
    temporal_correlation_min: Optional[float] = Field(None, ge=-1.0, le=1.0)
    contributor_count_min: Optional[int] = Field(None, ge=0)
    contributor_count_max: Optional[int] = Field(None, ge=0)
    upload_download_ratio_max: Optional[float] = Field(None, ge=0)
    window_index_range: Optional[List[int]] = Field(None, min_length=2, max_length=2)

    @field_validator(
        "intensity_range_mbps", "burstiness_pmr_range", "burstiness_cov_range"
    )
    @classmethod
    def _validate_range(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and v[0] > v[1]:
            raise ValueError("Range [min, max] must satisfy min <= max")
        return v


class SelectRequest(BaseModel):
    """Request body for ``POST /ctps/select``."""

    query: SelectQuery
    limit: int = Field(50, ge=1, le=10_000, description="Maximum results to return.")
    offset: int = Field(0, ge=0, description="Pagination offset.")
    order_by: str = Field(
        "intensity",
        description="Sort field: intensity | burstiness | contributor_count | window_index.",
    )

    @field_validator("order_by")
    @classmethod
    def _validate_order_by(cls, v: str) -> str:
        allowed = {"intensity", "burstiness", "contributor_count", "window_index"}
        if v not in allowed:
            raise ValueError(f"order_by must be one of {allowed}")
        return v


class SelectResponse(BaseModel):
    """Response body for ``POST /ctps/select``."""

    query_matched: int
    results_returned: int
    ctps: List[dict]


# ---------------------------------------------------------------------------
# Transform operation
# ---------------------------------------------------------------------------


class TransformRequest(BaseModel):
    """Request body for ``POST /ctps/transform``.

    Attributes:
        ctp_id: ID of the CTP to transform.
        output_dir: Directory to write the transformed PCAP files.
        throughput_threshold_mbps:hard cap (burst trimming).
            Packets in intervals exceeding this rate are randomly dropped.
        preserve_structure: When ``True`` (default), temporal shape and
            contributor structure are preserved; only intensity scales.
    """

    ctp_id: str
    output_dir: str
    users_root: str
    throughput_threshold_mbps: float = Field(..., gt=0)
    preserve_structure: bool = True


class TransformResponse(BaseModel):
    """Response body for ``POST /ctps/transform``."""

    original_ctp_id: str
    transformed_ctp_id: str
    throughput_threshold_mbps: float
    download_pcap: str
    upload_pcap: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Merge operation
# ---------------------------------------------------------------------------


class MergeRequest(BaseModel):
    """Request body for ``POST /ctps/merge``.

    Merges all /32 leaf CTPs under *subnet* across windows
    ``[start_index, end_index]`` into a single merged CTP with output PCAPs.

    Attributes:
        dataset_name: Dataset label.
        subnet: Parent CIDR subnet whose leaf nodes will be merged.
        start_index: First window index to include (inclusive).
        end_index: Last window index to include (inclusive).
        output_dir: Root directory for merged PCAP output.
            Files are written to ``<output_dir>/<dataset_name>_merged/``.
        users_root: Root of the per-user PCAP directory tree from extraction.
    """

    dataset_name: str
    subnet: str
    start_index: int = Field(..., ge=0)
    end_index: int = Field(..., ge=0)
    output_dir: str
    users_root: str

    @field_validator("end_index")
    @classmethod
    def _validate_index_range(cls, v: int, info) -> int:
        start = info.data.get("start_index")
        if start is not None and v < start:
            raise ValueError("end_index must be >= start_index")
        return v


class MergeResponse(BaseModel):
    """Response body for ``POST /ctps/merge``."""

    merged_ctp_id: str
    dataset_name: str
    subnet: str
    start_index: int
    end_index: int
    leaf_count: int
    merged_intensity_mbps: float
    merged_contributor_count: int
    download_pcap: str
    upload_pcap: str
    notes: Optional[str] = None
