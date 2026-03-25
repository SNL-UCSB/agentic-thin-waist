from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..models import WorkflowSpecification


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
