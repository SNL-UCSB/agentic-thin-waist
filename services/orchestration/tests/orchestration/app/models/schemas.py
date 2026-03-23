from enum import Enum
from typing import Any, Dict, List, Optional

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


class GeneratedExperiment(BaseModel):
    experiment_id: str
    capacity_mbps: float
    latency_ms: float
    loss_rate: float = 0.0
    application: str
    duration_seconds: int = 60
    num_trials: int = 1
    cc_algorithm: str = "cubic"
    aqm_policy: str = "fq_codel"
    ctp_cluster: Optional[str] = None
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
