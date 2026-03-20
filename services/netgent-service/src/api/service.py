"""Service helpers for querying NetGent persistence models."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from .models import AvailableWorkflows, WorkflowRun
from .schemas import (
    AvailableWorkflowItem,
    AvailableWorkflowsResponse,
    WorkflowResultResponse,
)


class NetGentService:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def get_available_workflows(self) -> AvailableWorkflowsResponse:
        with self._session_factory() as session:
            stmt = sa.select(AvailableWorkflows).order_by(
                AvailableWorkflows.application
            )
            rows = session.execute(stmt).scalars().all()
            return AvailableWorkflowsResponse(
                applications=[
                    AvailableWorkflowItem(
                        application=row.application,
                        notes=row.notes,
                    )
                    for row in rows
                ]
            )

    def get_workflow_status(self, workflow_id: UUID | str) -> WorkflowRun | None:
        workflow_uuid = UUID(str(workflow_id))
        with self._session_factory() as session:
            stmt = sa.select(WorkflowRun).where(WorkflowRun.id == workflow_uuid)
            return session.execute(stmt).scalar_one_or_none()

    def get_workflow_result(
        self, workflow_id: UUID | str
    ) -> WorkflowResultResponse | None:
        workflow = self.get_workflow_status(workflow_id)
        if workflow is None:
            return None
        return WorkflowResultResponse(
            workflow_id=str(workflow.id),
            status=workflow.status,
        )

    def get_available_workflow(
        self, workflow_id: UUID | str
    ) -> AvailableWorkflowItem | None:
        workflow_uuid = UUID(str(workflow_id))
        with self._session_factory() as session:
            stmt = (
                sa.select(AvailableWorkflows)
                .join(
                    WorkflowRun,
                    WorkflowRun.application_id == AvailableWorkflows.application_id,
                )
                .where(WorkflowRun.id == workflow_uuid)
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return None
            return AvailableWorkflowItem(
                application=row.application,
                notes=row.notes,
            )
