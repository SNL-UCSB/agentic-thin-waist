"""Pydantic models for the NetGent dummy API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


WorkflowStatus = Literal["executing", "completed", "failed", "timeout"]
ExecutionType = Literal["browser", "shell"]


class ExecuteWorkflowRequest(BaseModel):
    spec: str = Field(min_length=1)
    timeout: int = Field(default=120, ge=1)
    application: str = Field(min_length=1)
    llm_model: str | None = None
    headless: bool = True
    capture_artifacts: bool = True


class CompileWorkflowRequest(BaseModel):
    spec: str = Field(min_length=1)
    application: str | None = None


class ValidateWorkflowRequest(BaseModel):
    spec: str = Field(min_length=1)
    application: str | None = None


class WorkflowState(BaseModel):
    id: str
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class WorkflowTransition(BaseModel):
    from_state: str
    to_state: str
    condition: str | None = None


class ExecuteWorkflowResponse(BaseModel):
    workflow_id: str
    status: WorkflowStatus
    start_time: datetime
    estimated_completion: datetime


class CompileWorkflowResponse(BaseModel):
    workflow_id: str
    states: list[WorkflowState]
    transitions: list[WorkflowTransition]
    estimated_duration_seconds: int
    validation_status: str


class ValidateWorkflowResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    estimated_duration_seconds: int
    state_count: int


class NfaSummary(BaseModel):
    states: int
    transitions: int
    initial_state: str
    accepting_states: list[str]


class WorkflowArtifacts(BaseModel):
    har_file: str | None = None
    console_log: str | None = None
    screenshots: list[str] = Field(default_factory=list)


class WorkflowMetrics(BaseModel):
    video_startup_time_ms: int | None = None
    mean_bitrate_mbps: float | None = None
    rebuffer_events: int | None = None
    rebuffer_duration_ms: int | None = None
    bitrate_changes: int | None = None
    max_bitrate_mbps: float | None = None
    min_bitrate_mbps: float | None = None
    latency_ms: float | None = None
    packet_loss_percent: float | None = None
    throughput_mbps: float | None = None


class WorkflowResultResponse(BaseModel):
    workflow_id: str
    status: WorkflowStatus
    states_executed: list[str]
    duration: float
    nfa: NfaSummary
    artifacts: WorkflowArtifacts
    qoe_metrics: WorkflowMetrics
    errors: list[str] = Field(default_factory=list)


class AvailableWorkflowItem(BaseModel):
    application: str
    execution_type: ExecutionType
    supported_qoe_metrics: list[str]
    prerequisites: list[str] = Field(default_factory=list)
    notes: str


class AvailableWorkflowsResponse(BaseModel):
    applications: list[AvailableWorkflowItem]


class HealthChecks(BaseModel):
    browser_driver: str
    llm_service: str
    workflow_engine: str
    telemetry_service: str


class HealthResponse(BaseModel):
    status: str
    checks: HealthChecks
    uptime_seconds: int
