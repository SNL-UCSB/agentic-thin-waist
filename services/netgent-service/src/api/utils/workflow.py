from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..models import WorkflowJob, WorkflowSpecification


def create_workflow(
    session: Session,
    workflow_specification: WorkflowSpecification,
) -> WorkflowSpecification:
    session.add(workflow_specification)
    session.flush()
    return workflow_specification


def update_workflow(
    session: Session,
    workflow_id: str | UUID,
    *,
    specification: str | None = None,
    workflow_definition: dict[str, Any] | None = None,
    type: str | None = None,
) -> WorkflowSpecification:
    resolved_workflow_id = (
        UUID(workflow_id) if isinstance(workflow_id, str) else workflow_id
    )
    workflow = session.get(WorkflowSpecification, resolved_workflow_id)
    if workflow is None:
        raise ValueError(f"Workflow with id {workflow_id} not found")

    if specification is not None:
        workflow.specification = specification
    if workflow_definition is not None:
        workflow.workflow = workflow_definition
    if type is not None:
        workflow.type = type

    session.flush()
    return workflow


def get_workflow(
    session: Session,
    workflow_id: str | UUID,
) -> WorkflowSpecification | None:
    resolved_workflow_id = (
        UUID(workflow_id) if isinstance(workflow_id, str) else workflow_id
    )
    return session.get(WorkflowSpecification, resolved_workflow_id)


def list_workflow_summaries(session: Session) -> list[dict[str, Any]]:
    latest_runs = (
        sa.select(
            WorkflowJob.workflow_id.label("workflow_id"),
            sa.func.max(WorkflowJob.created_at).label("last_executed_at"),
        )
        .where(WorkflowJob.workflow_id.is_not(None))
        .group_by(WorkflowJob.workflow_id)
        .subquery()
    )

    statement = (
        sa.select(
            WorkflowSpecification.id.label("workflow_id"),
            WorkflowSpecification.specification,
            latest_runs.c.last_executed_at,
        )
        .outerjoin(latest_runs, WorkflowSpecification.id == latest_runs.c.workflow_id)
        .order_by(
            latest_runs.c.last_executed_at.desc().nulls_last(),
            WorkflowSpecification.created_at.desc(),
        )
    )

    rows = session.execute(statement).all()
    return [
        {
            "workflow_id": str(workflow_id),
            "specification": specification,
            "last_executed_at": last_executed_at,
        }
        for workflow_id, specification, last_executed_at in rows
    ]
