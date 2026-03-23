from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from ..models import WorkflowJob
from ..schemas import WorkflowStatus


def create_job(session: Session, workflow_job: WorkflowJob) -> WorkflowJob:
    session.add(workflow_job)
    session.flush()
    return workflow_job


def update_job_status(
    session: Session,
    job_id: str | UUID,
    status: WorkflowStatus,
) -> WorkflowJob:
    resolved_job_id = UUID(job_id) if isinstance(job_id, str) else job_id
    job = session.get(WorkflowJob, resolved_job_id)
    if job is None:
        raise ValueError(f"Job with id {job_id} not found")
    job.status = status
    session.flush()
    return job


def get_job(session: Session, job_id: str | UUID) -> WorkflowJob | None:
    resolved_job_id = UUID(job_id) if isinstance(job_id, str) else job_id
    return session.get(WorkflowJob, resolved_job_id)
