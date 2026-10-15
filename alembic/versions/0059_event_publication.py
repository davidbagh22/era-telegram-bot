"""Persist quick event drafts and the public announcement outbox."""
from alembic import op
import sqlalchemy as sa

revision = "0059_event_publication"
down_revision = "0058_book_club"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("event_experiences")}
    for name, length, default in (("creation_mode", 16, "wizard"), ("announcement_status", 24, "not_requested")):
        if name not in columns:
            op.add_column("event_experiences", sa.Column(name, sa.String(length), nullable=False, server_default=default))
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("event_experiences")}
    if "ix_event_experiences_announcement_status" not in indexes:
        op.create_index("ix_event_experiences_announcement_status", "event_experiences", ["announcement_status"])


def downgrade() -> None:
    op.drop_index("ix_event_experiences_announcement_status", table_name="event_experiences")
    op.drop_column("event_experiences", "announcement_status")
    op.drop_column("event_experiences", "creation_mode")
