"""Add partner initiative start timestamp."""

from alembic import op
import sqlalchemy as sa

revision = "0004_partner_initiative_starts_at"
down_revision = "0003_partners_and_profile_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("partner_initiatives", sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("partner_initiatives", "starts_at")
