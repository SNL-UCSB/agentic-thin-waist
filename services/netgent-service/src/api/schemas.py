"""Pydantic models for the NetGent dummy API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

WorkflowStatus = Literal["pending", "running", "completed", "failed", "timeout"]
HealthStatus = Literal["healthy", "unhealthy"]


class GenerateWorkflowRequest(BaseModel):
    specification: str = Field(min_length=1)
    timeout: int | None = Field(default=None, ge=1)
    type: Literal["shell", "browser", "hybrid"] = "shell"


class GenerateWorkflowResponse(BaseModel):
    workflow_id: str
    job_id: str
    status: WorkflowStatus
    error: str | None = None


class HealthResponse(BaseModel):
    status: HealthStatus


class ExecuteWorkflowRequest(BaseModel):
    workflow_id: str
    timeout: int | None = Field(default=None, ge=1)
    parameters: dict[str, str] = Field(default_factory=dict)


class ExecuteWorkflowResponse(BaseModel):
    job_id: str
    workflow_id: str
    status: WorkflowStatus
    error: str | None = None


class WorkflowResultResponse(BaseModel):
    workflow_id: str
    job_id: str
    status: WorkflowStatus
    metadata: dict[str, Any] = Field(default_factory=dict)


class AvailableWorkflowItem(BaseModel):
    workflow_id: str
    specification: str
    last_executed_at: datetime | None = None
    parameters: list[str] = Field(default_factory=list)


class AvailableWorkflowsResponse(BaseModel):
    workflows: list[AvailableWorkflowItem]
