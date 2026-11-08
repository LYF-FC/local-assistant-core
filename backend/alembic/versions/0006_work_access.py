"""Synthetic work identity registry; no work content storage or implicit grants.

Revision ID: 0006_work_access
Revises: 0005_scoped_memory
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_work_access"
down_revision = "0005_scoped_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "work_workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(64), unique=True, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "work_access_grants",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("work_workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("capability", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("capability = 'work_private'", name="ck_work_capability"),
    )


def downgrade():
    op.drop_table("work_access_grants")
    op.drop_table("work_workspaces")
