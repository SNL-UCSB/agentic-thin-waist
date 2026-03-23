"""Workflow routes for the NetGent API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status


from ..schemas import (
    AvailableWorkflowsResponse,
    GenerateWorkflowRequest,
    GenerateWorkflowResponse,
    ExecuteWorkflowRequest,
    ExecuteWorkflowResponse,
    WorkflowResultResponse,
)
from ..services.workflow import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflow"])


# Generate a Workflow (Similar to the Compile Endpoint) -> It will generate an NFA Workflow based in Natural Language Specification
@router.post(
    "/generate",
    response_model=GenerateWorkflowResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_workflow(
    request: GenerateWorkflowRequest,
    service: WorkflowService = Depends(WorkflowService),
) -> GenerateWorkflowResponse:
    return service.generate(request)


@router.post("/execute", response_model=ExecuteWorkflowResponse)
def execute_workflow(
    request: ExecuteWorkflowRequest,
    service: WorkflowService = Depends(WorkflowService),
) -> ExecuteWorkflowResponse:
    return service.execute(request)


@router.get(
    "/available",
    response_model=AvailableWorkflowsResponse,
)
def get_applications(
    service: WorkflowService = Depends(WorkflowService),
) -> AvailableWorkflowsResponse:
    return service.get_available()


@router.get(
    "/result/{job_id}",
    response_model=WorkflowResultResponse,
)
def get_result(
    job_id: str,
    service: WorkflowService = Depends(WorkflowService),
) -> WorkflowResultResponse:
    return service.get_result(job_id)
