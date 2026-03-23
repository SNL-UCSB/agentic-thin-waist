from __future__ import annotations

from uuid import UUID, uuid4

import sqlalchemy as sa

from ..models import AvailableWorkflows, WorkflowJob, WorkflowSpecification
from ..schemas import (
    AvailableWorkflowItem,
    AvailableWorkflowsResponse,
    ExecuteWorkflowRequest,
    ExecuteWorkflowResponse,
    GenerateWorkflowRequest,
    GenerateWorkflowResponse,
    WorkflowResultResponse,
)
from ..utils import create_session_factory


class WorkflowService:
    def __init__(self):
        self.session_factory = create_session_factory()

    def generate(self, request: GenerateWorkflowRequest) -> GenerateWorkflowResponse:
        with self.session_factory() as session:
            available_workflow = session.execute(
                sa.select(AvailableWorkflows).where(
                    AvailableWorkflows.name == request.application
                )
            ).scalar_one_or_none()
            if available_workflow is None:
                return GenerateWorkflowResponse(
                    workflow_id="",
                    job_id="",
                    status="failed",
                    error=f"Unsupported Application Error: {request.application}",
                )

            specification = WorkflowSpecification(
                id=uuid4(),
                application_id=available_workflow.id,
                specification=request.specification,
                workflow={},  # Will be Filled Later
            )
            session.add(specification)
            session.flush()

            job = WorkflowJob(
                id=uuid4(),
                application_id=available_workflow.id,
                workflow_id=specification.id,
                status="pending",
                metadata_={
                    "timeout": request.timeout,
                },
                parameters=request.parameters,
            )
            session.add(job)
            session.commit()

            # Call Generate Workflow Here

            return GenerateWorkflowResponse(
                workflow_id=str(specification.id),
                job_id=str(job.id),
                status=job.status,
            )

    def execute(self, request: ExecuteWorkflowRequest) -> ExecuteWorkflowResponse:
        try:
            workflow_uuid = UUID(request.workflow_id)
        except ValueError:
            return ExecuteWorkflowResponse(
                job_id="",
                workflow_id=request.workflow_id,
                status="failed",
                error="Invalid workflow_id",
            )

        with self.session_factory() as session:
            specification = session.execute(
                sa.select(WorkflowSpecification).where(
                    WorkflowSpecification.id == workflow_uuid
                )
            ).scalar_one_or_none()
            if specification is None:
                return ExecuteWorkflowResponse(
                    job_id="",
                    workflow_id=request.workflow_id,
                    status="failed",
                    error="Workflow not found",
                )

            job = WorkflowJob(
                id=uuid4(),
                application_id=specification.application_id,
                workflow_id=specification.id,
                status="pending",
                metadata_={"timeout": request.timeout},
                parameters=request.parameters,
            )
            session.add(job)
            session.commit()

            # Call Execute Workflow Here

            return ExecuteWorkflowResponse(
                job_id=str(job.id),
                workflow_id=str(specification.id),
                status=job.status,
            )

    def get_result(self, job_id: str) -> WorkflowResultResponse:
        try:
            job_uuid = UUID(job_id)
        except ValueError:
            return WorkflowResultResponse(
                workflow_id="",
                job_id=job_id,
                status="failed",
                metadata={"error": "Invalid job_id"},
            )
        with self.session_factory() as session:
            job = (
                session.execute(
                    sa.select(WorkflowJob)
                    .where(WorkflowJob.id == job_uuid)
                    .order_by(WorkflowJob.created_at.desc())
                )
                .scalars()
                .first()
            )
            if job is None:
                return WorkflowResultResponse(
                    workflow_id="",
                    job_id=job_id,
                    status="failed",
                    metadata={"error": "Job not found"},
                )

            return WorkflowResultResponse(
                workflow_id=str(job.workflow_id),
                job_id=str(job.id),
                status=job.status,
                metadata=job.metadata_,
            )

    def get_available(self) -> AvailableWorkflowsResponse:
        with self.session_factory() as session:
            available_workflows = (
                session.execute(sa.select(AvailableWorkflows)).scalars().all()
            )
            return AvailableWorkflowsResponse(
                applications=[
                    AvailableWorkflowItem(
                        application=available_workflow.name,
                        notes=available_workflow.notes,
                    )
                    for available_workflow in available_workflows
                ]
            )
