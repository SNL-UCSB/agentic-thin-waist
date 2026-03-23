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
from ..utils import (
    create_job,
    create_session_factory,
    create_workflow,
    get_job,
    get_workflow,
    update_job_status,
)
from ..worker.queue.app import run_netgent


class WorkflowService:
    def __init__(self):
        self.session_factory = create_session_factory()

    def _defer_job(self, session, job: WorkflowJob) -> str | None:
        try:
            run_netgent.defer(job_id=str(job.id))
        except Exception as exc:
            update_job_status(session, job.id, "failed")
            metadata = dict(job.metadata_ or {})
            metadata["error"] = f"Failed to queue job: {exc}"
            job.metadata_ = metadata
            session.commit()
            return str(exc)
        return None

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

            specification = create_workflow(
                session,
                WorkflowSpecification(
                    id=uuid4(),
                    application_id=available_workflow.id,
                    specification=request.specification,
                    workflow={},  # Will be Filled Later
                ),
            )

            job = create_job(
                session,
                WorkflowJob(
                    id=uuid4(),
                    application_id=available_workflow.id,
                    workflow_id=specification.id,
                    status="pending",
                    metadata_={
                        "timeout": request.timeout,
                    },
                    parameters=request.parameters,
                ),
            )
            session.commit()

            defer_error = self._defer_job(session, job)
            if defer_error is not None:
                return GenerateWorkflowResponse(
                    workflow_id=str(specification.id),
                    job_id=str(job.id),
                    status="failed",
                    error=defer_error,
                )

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
            specification = get_workflow(session, workflow_uuid)
            if specification is None:
                return ExecuteWorkflowResponse(
                    job_id="",
                    workflow_id=request.workflow_id,
                    status="failed",
                    error="Workflow not found",
                )

            job = create_job(
                session,
                WorkflowJob(
                    id=uuid4(),
                    application_id=specification.application_id,
                    workflow_id=specification.id,
                    status="pending",
                    metadata_={"timeout": request.timeout},
                    parameters=request.parameters,
                ),
            )
            session.commit()

            defer_error = self._defer_job(session, job)
            if defer_error is not None:
                return ExecuteWorkflowResponse(
                    job_id=str(job.id),
                    workflow_id=str(specification.id),
                    status="failed",
                    error=defer_error,
                )

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
            job = get_job(session, job_uuid)
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
