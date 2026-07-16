from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class OrchestrationStatus(str, Enum):
    pending = "pending"
    parsing = "parsing"
    generating = "generating"
    validating = "validating"
    executing = "executing"
    complete = "complete"
    failed = "failed"


class ResearchIntent(BaseModel):
    intent: str = Field(..., description="Natural language research goal")
    context: Dict[str, Any] = Field(default_factory=dict)
    preferences: Dict[str, Any] = Field(default_factory=dict)
    workflow_source: Literal["auto", "library", "generate"] = Field(
        default="auto",
        description=(
            "Where the workflow comes from. "
            "'auto' (default): LLM picks a match from the library, falls back to "
            "generation if no match. "
            "'library': LLM picks from the library only; fail if no match. "
            "'generate': skip the library, always have the LLM generate."
        ),
    )
    workflow_id: Optional[str] = Field(
        default=None,
        description=(
            "Explicit workflow id to use (e.g. 'test_ndt_workflow'). "
            "When set, overrides workflow_source."
        ),
    )


class ApplicationConfig(BaseModel):
    """Application-specific network settings retained in an experiment spec."""

    application: str
    latency_ms: float = Field(..., ge=0)


class GeneratedExperiment(BaseModel):
    experiment_id: str
    application_type: Literal["shell", "browser", "mixed"] = "shell"
    capacity_mbps: float
    latency_ms: float
    application_configs: List[ApplicationConfig] = Field(
        default_factory=list,
        description=(
            "Per-application network settings for concurrent execution. Empty "
            "means the global latency_ms applies to all application traffic."
        ),
    )
    loss_rate: float = 0.0
    duration_seconds: int = 60
    num_trials: int = 1
    cc_algorithm: str = "cubic"
    aqm_policy: str = "pfifo"
    applications: List[str] = Field(
        default_factory=list,
        description=(
            "Application names for this experiment (e.g. ['youtube', 'ndt']). "
            "Empty list means single-app mode using application_type."
        ),
    )
    application_types: List[Literal["shell", "browser"]] = Field(
        default_factory=list,
        description=(
            "Per-app runtime type, positionally aligned with 'applications'. "
            "Empty when applications is empty."
        ),
    )
    execution_mode: Literal["isolated", "concurrent"] = Field(
        "isolated",
        description=(
            "'isolated' runs a single application per worker (default). "
            "'concurrent' runs multiple applications simultaneously on the "
            "same worker under the same bottleneck conditions."
        ),
    )
    buffer_packets: Optional[int] = Field(
        default=None,
        description=(
            "Bottleneck queue size in packets for pfifo / bfifo / sfq qdiscs. "
            "Forwarded as ShapeRequest.buffer_packets. None → substrate-worker "
            "default (1000)."
        ),
    )
    qdisc_params: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "Per-qdisc tuning forwarded as ShapeRequest.qdisc_params "
            "(e.g. {'limit': '500'} for AQM qdiscs)."
        ),
    )
    ctp_cluster: Optional[str] = None
    ctp_capacity_range: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            "Optional CTP capacity range in Mbps for selecting background "
            "cross-traffic. None means no CTP replay for this experiment."
        ),
    )
    replay_pnat_ip: Optional[str] = Field(
        default=None,
        description=(
            "Optional target IP for tcpreplay PNAT rewrite (e.g. '172.16.1.20'). "
            "When set, replayed CTP source IPs are mapped to this address; the "
            "standard source subnets (169.231.0.0/16, 128.111.0.0/16) are reused. "
            "Leave unset to use the orchestrator default (172.16.1.20). Must not "
            "conflict with the application IP."
        ),
    )
    reasoning: str = ""


class OrchestrationResponse(BaseModel):
    orchestration_id: str
    status: OrchestrationStatus
    intent: str
    generated_experiments: int
    estimated_duration_minutes: Optional[float] = None
    claude_model: str = "claude-sonnet-4-6"


class ReasoningStep(BaseModel):
    step: int
    action: str
    input: Dict[str, Any]
    output: Dict[str, Any]
    reasoning: str


class OrchestrationProgress(BaseModel):
    orchestration_id: str
    status: OrchestrationStatus
    progress: Dict[str, Any]
    generated_experiments: List[Dict[str, Any]]


class OrchestrationResult(BaseModel):
    orchestration_id: str
    intent: str
    status: OrchestrationStatus
    experiment_results: List[Dict[str, Any]]
    summary: Dict[str, Any]
