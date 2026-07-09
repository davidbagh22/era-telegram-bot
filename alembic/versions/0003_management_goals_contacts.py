"""Add management goals and organization contacts."""

import sqlalchemy as sa
from alembic import op

revision = "0003_management_goals_contacts"
down_revision = "0002_era_v2_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("scope_type", sa.String(32), server_default="global", nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_value", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_value", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_monthly_goals_month", "monthly_goals", ["month"])
    op.create_index("ix_monthly_goals_scope_type", "monthly_goals", ["scope_type"])
    op.create_index("ix_monthly_goals_scope_id", "monthly_goals", ["scope_id"])
    op.create_index("ix_monthly_goals_status", "monthly_goals", ["status"])

    op.create_table(
        "organization_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("position", sa.String(255), nullable=True),
        sa.Column("second_contact_name", sa.String(255), nullable=True),
        sa.Column("second_position", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_organization_contacts_organization_name", "organization_contacts", ["organization_name"])
    op.create_index("ix_organization_contacts_email", "organization_contacts", ["email"])
    op.create_index("ix_organization_contacts_is_active", "organization_contacts", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_organization_contacts_is_active", table_name="organization_contacts")
    op.drop_index("ix_organization_contacts_email", table_name="organization_contacts")
    op.drop_index("ix_organization_contacts_organization_name", table_name="organization_contacts")
    op.drop_table("organization_contacts")
    op.drop_index("ix_monthly_goals_status", table_name="monthly_goals")
    op.drop_index("ix_monthly_goals_scope_id", table_name="monthly_goals")
    op.drop_index("ix_monthly_goals_scope_type", table_name="monthly_goals")
    op.drop_index("ix_monthly_goals_month", table_name="monthly_goals")
    op.drop_table("monthly_goals")
