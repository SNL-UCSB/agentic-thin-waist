"""Workflow routes for the NetGent API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from botocore.client import BaseClient
from sqlalchemy.orm import sessionmaker

from ..exceptions import UnsupportedApplicationError
from ..service import NetGentService
from ..schemas import (
    AvailableWorkflowsResponse,
    GenerateWorkflowRequest,
    GenerateWorkflowResponse,
    WorkflowStatusResponse,
    WorkflowResultResponse,
)

router = APIRouter(prefix="/workflows", tags=["workflow"])


def get_netgent_service(request: Request) -> NetGentService:
    session_factory = sessionmaker(
        bind=request.app.state.db_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    s3_client: BaseClient = request.app.state.s3_client
    s3_bucket_name: str = request.app.state.s3_bucket_name
    return NetGentService(session_factory, s3_client, s3_bucket_name)


# Generate a Workflow
@router.post(
    "/generate",
    response_model=GenerateWorkflowResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_workflow(
    request: GenerateWorkflowRequest,
    service: NetGentService = Depends(get_netgent_service),
) -> GenerateWorkflowResponse:
    try:
        workflow = service.generate_workflow(request)
    except UnsupportedApplicationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return GenerateWorkflowResponse(
        workflow_id=str(workflow.id),
        status=workflow.status,
    )


# Get the Status of a Workflow
@router.get("/status/{workflow_id}", response_model=WorkflowStatusResponse)
def get_workflow_status(
    workflow_id: str,
    service: NetGentService = Depends(get_netgent_service),
) -> WorkflowStatusResponse:
    try:
        workflow = service.get_workflow_status(workflow_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workflow ID",
        ) from exc
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found"
        )
    return WorkflowStatusResponse(
        workflow_id=str(workflow.id),
        status=workflow.status,
    )


@router.get(
    "/available",
    response_model=AvailableWorkflowsResponse,
)
def get_available_workflows(
    service: NetGentService = Depends(get_netgent_service),
) -> AvailableWorkflowsResponse:
    return service.get_available_workflows()


@router.get(
    "/result/{workflow_id}",
    response_model=WorkflowResultResponse,
)
def get_workflow_result(
    workflow_id: str,
    service: NetGentService = Depends(get_netgent_service),
) -> WorkflowResultResponse:
    try:
        workflow_result = service.get_workflow_result(workflow_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workflow ID",
        ) from exc
    if workflow_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found"
        )
    return workflow_result
