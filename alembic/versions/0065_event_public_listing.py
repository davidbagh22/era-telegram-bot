"""Reversible event public-listing flag; preserve all existing event data."""
from alembic import op
import sqlalchemy as sa

revision = "0065_event_public_listing"
down_revision = "0064_telegram_analytics"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "event_experiences" not in inspector.get_table_names():
        raise RuntimeError("event_experiences table missing; cannot set public visibility")
    columns = {column["name"] for column in inspector.get_columns("event_experiences")}
    if "show_in_public_listing" not in columns:
        op.add_column(
            "event_experiences",
            sa.Column("show_in_public_listing", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade():
    # The flag may hold deliberate visibility decisions; dropping it would
    # re-expose hidden events. Roll back application code, not user choices.
    raise NotImplementedError("Do not drop event visibility decisions without owner approval")
