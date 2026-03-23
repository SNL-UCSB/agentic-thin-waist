"""Internal SQLAlchemy persistence models for NetGent."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class WorkflowSpecification(Base):
    """Persisted workflow specification."""

    __tablename__ = "workflow_specifications"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("available_workflows.id"),
        nullable=False,
        index=True,
    )
    workflow = sa.Column(
        sa.JSON,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::json"),
    )
    specification = sa.Column(sa.Text, nullable=False)
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

    application = relationship(
        "AvailableWorkflows",
        back_populates="workflow_specifications",
    )
    workflow_runs = relationship(
        "WorkflowJob",
        back_populates="workflow_specification",
        cascade="all, delete-orphan",
    )


class WorkflowJob(Base):
    """Persisted workflow execution record."""

    __tablename__ = "workflow_runs"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("available_workflows.id"),
        nullable=False,
        index=True,
    )
    workflow_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("workflow_specifications.id"),
        nullable=True,
        index=True,
    )
    status = sa.Column(sa.String(32), nullable=False, index=True)
    metadata_ = sa.Column("metadata", JSONB, nullable=False, default=dict)
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

    workflow_specification = relationship(
        "WorkflowSpecification",
        back_populates="workflow_runs",
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

    workflow = relationship("WorkflowJob", back_populates="artifacts")


class AvailableWorkflows(Base):
    __tablename__ = "available_workflows"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = sa.Column(sa.String(128), nullable=False, unique=True, index=True)
    notes = sa.Column(sa.Text, nullable=False)
    prompt = sa.Column(sa.Text, nullable=False)

    workflow_specifications = relationship(
        "WorkflowSpecification",
        back_populates="application",
        cascade="all, delete-orphan",
    )
    workflow_runs = relationship("WorkflowJob", back_populates="application")
