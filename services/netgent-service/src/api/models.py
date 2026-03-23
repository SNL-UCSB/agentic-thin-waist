"""Internal SQLAlchemy and Pydantic models for NetGent persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class WorkflowRun(Base):
    """Persisted workflow execution record."""

    __tablename__ = "workflow_runs"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("available_workflows.application_id"),
        nullable=False,
        index=True,
    )
    query = sa.Column(sa.Text, nullable=False)
    status = sa.Column(sa.String(32), nullable=False, index=True)
    metadata_ = sa.Column("metadata", JSONB, nullable=False, default=dict)
    workflow = sa.Column(
        sa.JSON,
        nullable=True,
        default=dict,
        server_default=sa.text("'{}'::json"),
    )
    parameters = sa.Column(
        sa.JSON,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::json"),
    )
    created_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    artifacts = relationship("WorkflowArtifact", back_populates="workflow")
    application = relationship("AvailableWorkflows", back_populates="workflow_runs")


class WorkflowArtifact(Base):
    """Persisted artifact metadata for a workflow run."""

    __tablename__ = "workflow_artifacts"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = sa.Column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    workflow = relationship("WorkflowRun", back_populates="artifacts")


class AvailableWorkflows(Base):
    __tablename__ = "available_workflows"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id = sa.Column(
        UUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    application = sa.Column(sa.String(128), nullable=False, index=True)
    notes = sa.Column(sa.Text, nullable=False)
    prompt = sa.Column(sa.Text, nullable=False)

    workflow_runs = relationship("WorkflowRun", back_populates="application")
