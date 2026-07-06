"""Add partners."""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_partners"
down_revision = "0002_social_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partners",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(64), nullable=True),
        sa.Column("telegram_url", sa.String(500), nullable=True),
        sa.Column("logo_file_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "partner_initiatives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("partner_id", sa.Integer(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "partner_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("partner_id", sa.Integer(), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("partner_tasks")
    op.drop_table("partner_initiatives")
    op.drop_table("partners")
