"""Pydantic models for the NetGent dummy API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


WorkflowStatus = Literal["pending", "running", "completed", "failed", "timeout"]
HealthStatus = Literal["healthy", "unhealthy"]


class GenerateWorkflowRequest(BaseModel):
    query: str = Field(min_length=1)
    parameters: dict[str, str] = Field(default_factory=dict)
    timeout: int | None = Field(default=None, ge=1)
    application: str = Field(min_length=1)


class WorkflowState(BaseModel):
    id: str
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class WorkflowTransition(BaseModel):
    from_state: str
    to_state: str
    condition: str | None = None


class GenerateWorkflowResponse(BaseModel):
    workflow_id: str
    status: WorkflowStatus


class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    status: WorkflowStatus


class WorkflowResultResponse(BaseModel):
    workflow_id: str
    status: WorkflowStatus
    metadata: dict[str, Any] = Field(default_factory=dict)


class AvailableWorkflowItem(BaseModel):
    application: str
    notes: str


class AvailableWorkflowsResponse(BaseModel):
    applications: list[AvailableWorkflowItem]


class HealthResponse(BaseModel):
    status: HealthStatus
