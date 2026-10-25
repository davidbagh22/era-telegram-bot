"""Add ERA PRO application workflow.

Revision ID: 0044_era_pro
Revises: 0043_incident_generation
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0044_era_pro"
down_revision = "0043_incident_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "era_pro_applications" in inspector.get_table_names():
        return

    op.create_table(
        "era_pro_applications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="submitted"),
        sa.Column("motivation", sa.Text(), nullable=False),
        sa.Column("directions", sa.JSON(), nullable=False),
        sa.Column("target_result", sa.Text(), nullable=False),
        sa.Column("community_value", sa.Text(), nullable=False),
        sa.Column("portfolio_url", sa.String(length=1000), nullable=True),
        sa.Column("admin_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_era_pro_applications_user_id", "era_pro_applications", ["user_id"])
    op.create_index("ix_era_pro_applications_user_created", "era_pro_applications", ["user_id", "created_at"])
    op.create_index("ix_era_pro_applications_status_created", "era_pro_applications", ["status", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if "era_pro_applications" in sa.inspect(bind).get_table_names():
        op.drop_table("era_pro_applications")
