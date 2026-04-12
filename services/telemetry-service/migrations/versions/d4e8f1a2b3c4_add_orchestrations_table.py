"""add orchestrations table

Revision ID: d4e8f1a2b3c4
Revises: c79519a4a683
Create Date: 2026-04-11

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4e8f1a2b3c4"
down_revision = "c79519a4a683"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "orchestrations",
        sa.Column("orchestration_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("orchestration_id"),
    )


def downgrade():
    op.drop_table("orchestrations")
