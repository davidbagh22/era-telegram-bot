"""Monthly goals and organization contacts."""

import sqlalchemy as sa
from alembic import op

revision = "0003_management_tools"
down_revision = "0002_era_v2_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("scope_type", sa.String(32), server_default="department", nullable=False),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id")),
        sa.Column("direction_id", sa.Integer(), sa.ForeignKey("directions.id")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("metric", sa.String(100), server_default="Результат", nullable=False),
        sa.Column("target_value", sa.Integer(), server_default="1", nullable=False),
        sa.Column("actual_value", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_monthly_goals_period", "monthly_goals", ["period"])
    op.create_index("ix_monthly_goals_scope_type", "monthly_goals", ["scope_type"])
    op.create_index("ix_monthly_goals_status", "monthly_goals", ["status"])

    op.create_table(
        "organization_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization", sa.String(255)),
        sa.Column("contact_name", sa.String(255)),
        sa.Column("position_primary", sa.String(255)),
        sa.Column("position_secondary", sa.String(255)),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(64)),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_organization_contacts_organization", "organization_contacts", ["organization"])
    op.create_index("ix_organization_contacts_contact_name", "organization_contacts", ["contact_name"])
    op.create_index("ix_organization_contacts_email", "organization_contacts", ["email"])
    op.create_index("ix_organization_contacts_is_active", "organization_contacts", ["is_active"])


def downgrade() -> None:
    op.drop_table("organization_contacts")
    op.drop_table("monthly_goals")
