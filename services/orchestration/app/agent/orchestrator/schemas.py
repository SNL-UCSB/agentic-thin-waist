"""Pydantic schemas for the Orchestrator Agent."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ParsedIntent(BaseModel):
    """Structured output from IntentParser — Claude's extraction of experiment parameters."""

    applications: List[str] = Field(
        ..., description="Application names (e.g. youtube, ndt, ping)"
    )
    application_type: Literal["shell", "browser"] = Field(
        "shell",
        description="Runtime type: 'shell' for CLI tools (ndt, iperf, ping, speedtest) or 'browser' for web applications (youtube, zoom, browsing)",
    )
    capacities: Optional[List[float]] = Field(
        None, description="Link capacities in Mbps"
    )
    latencies: Optional[List[float]] = Field(None, description="Latency values in ms")
    cc_algorithms: Optional[List[str]] = Field(
        None, description="Congestion control algorithms (e.g. cubic, bbr)"
    )
    aqm_policy: Optional[str] = Field(
        None, description="AQM policy (e.g. fq_codel, fifo)"
    )
    buffer_packets: Optional[int] = Field(
        None,
        description=(
            "Bottleneck queue size in PACKETS for pfifo / bfifo / sfq qdiscs. "
            "Extract from intent phrases like 'queue size 100 packets' or "
            "'buffer of 50 packets'. Ignored for AQM qdiscs (use qdisc_params.limit)."
        ),
    )
    qdisc_params: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "Per-qdisc tuning passed to tc (e.g. {'limit': '500', 'target': '5ms', "
            "'interval': '100ms'} for fq_codel/codel/cake). For AQM qdiscs, 'limit' "
            "sets the queue size."
        ),
    )
    ctp_cluster: Optional[str] = Field(
        None, description="Cross-traffic profile cluster id"
    )
    ctp_capacity_range: Optional[Dict[str, float]] = Field(
        default_factory=lambda: {"lower_value": 1.0, "higher_value": 10.0},
        description=(
            "Optional CTP capacity range in Mbps used for CTP selection only. "
            "Keys: lower_value, higher_value."
        ),
    )
    duration_seconds: Optional[int] = Field(
        None, description="Experiment duration in seconds"
    )
    workflow_parameters: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Optional workflow-specific parameter overrides inferred from intent "
            "(e.g., for NDT: {'download': true, 'upload': false} for 'download only')."
        ),
    )
    num_trials: int = Field(1, description="Number of repeated trials")
    clarification_needed: List[str] = Field(
        default_factory=list,
        description="Questions for the user when intent is ambiguous",
    )
    design_type: List[str] = Field(
        default_factory=list,
        description="Per-experiment design type: isolated | concurrent | full | needs_clarification",
    )
    reasoning: str = Field("", description="Claude's explanation of its interpretation")
