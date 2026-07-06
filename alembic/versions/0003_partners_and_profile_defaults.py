"""Add partners."""

from alembic import op
import sqlalchemy as sa

revision = "0003_partners_and_profile_defaults"
down_revision = "0002_social_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("partners", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("source_url", sa.String(500), nullable=True), sa.Column("status", sa.String(32), nullable=False), sa.Column("notes", sa.Text(), nullable=True), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("partners")
