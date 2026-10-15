"""Allow Telegram supergroup identifiers in Media records."""
from alembic import op
import sqlalchemy as sa

revision = "0060_media_chat_bigint"
down_revision = "0059_event_publication"
branch_labels = None
depends_on = None


def _resize(widen: bool) -> None:
    for table, column in (("media_attachments", "source_chat_id"), ("media_chat_activity", "chat_id")):
        field = next(item for item in sa.inspect(op.get_bind()).get_columns(table) if item["name"] == column)
        if isinstance(field["type"], sa.BigInteger) == widen:
            continue
        target = sa.BigInteger() if widen else sa.Integer()
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, existing_type=field["type"], type_=target,
                               existing_nullable=field["nullable"])


def upgrade() -> None:
    _resize(True)


def downgrade() -> None:
    # PostgreSQL refuses narrowing if real Telegram IDs no longer fit int32.
    _resize(False)
