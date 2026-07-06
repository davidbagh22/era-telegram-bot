"""Repair timestamp defaults."""

from alembic import op
import sqlalchemy as sa

revision = "0005_social_timestamp_defaults"
down_revision = "0004_partner_initiative_starts_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("social_profiles", "created_at", existing_type=sa.DateTime(timezone=True), server_default=sa.func.now(), existing_nullable=False)
    op.alter_column("social_profiles", "updated_at", existing_type=sa.DateTime(timezone=True), server_default=sa.func.now(), existing_nullable=False)
    op.alter_column("social_links", "created_at", existing_type=sa.DateTime(timezone=True), server_default=sa.func.now(), existing_nullable=False)
    op.alter_column("social_links", "updated_at", existing_type=sa.DateTime(timezone=True), server_default=sa.func.now(), existing_nullable=False)


def downgrade() -> None:
    pass
