"""Add opt-in flag for daily book club, on existing and fresh databases."""
from alembic import op
import sqlalchemy as sa

revision = "0058_book_club"
down_revision = "0057_pulse_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("users")}
    if "book_club_subscribed" not in columns:
        op.add_column(
            "users",
            sa.Column("book_club_subscribed", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    index_names = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("users")}
    if "ix_users_book_club_subscribed" not in index_names:
        op.create_index("ix_users_book_club_subscribed", "users", ["book_club_subscribed"])


def downgrade() -> None:
    # Do not remove an opt-in flag that can predate this migration on an
    # existing database; manual backup-based downgrade is required.
    raise NotImplementedError("0058 rollback requires a backup and manual review")
