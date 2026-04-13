"""expand results.application column length

Revision ID: e8a1c2d3f4a5
Revises: d4e8f1a2b3c4
Create Date: 2026-04-13

"""

from alembic import op
import sqlalchemy as sa

revision = "e8a1c2d3f4a5"
down_revision = "d4e8f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("results", schema=None) as batch_op:
        batch_op.alter_column(
            "application",
            existing_type=sa.String(length=32),
            type_=sa.String(length=256),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table("results", schema=None) as batch_op:
        batch_op.alter_column(
            "application",
            existing_type=sa.String(length=256),
            type_=sa.String(length=32),
            existing_nullable=True,
        )
