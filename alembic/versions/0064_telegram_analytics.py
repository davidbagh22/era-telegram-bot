"""Minimal idempotent Telegram observation ledger, no backfilled history."""
from alembic import op
import sqlalchemy as sa

revision = "0064_telegram_analytics"
down_revision = "0063_certificates"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "telegram_message_facts" not in tables:
        op.create_table("telegram_message_facts",
            sa.Column("chat_id", sa.BigInteger(), primary_key=True),
            sa.Column("message_id", sa.BigInteger(), primary_key=True),
            sa.Column("media_group_id", sa.String(100)),
            sa.Column("topic_id", sa.Integer()),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("edited_at", sa.DateTime(timezone=True)),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source_type", sa.String(24), nullable=False),
            sa.Column("deleted_state", sa.String(16), nullable=False))
    indexes = {item['name'] for item in sa.inspect(op.get_bind()).get_indexes("telegram_message_facts")}
    if "ix_telegram_fact_chat_time" not in indexes:
        op.create_index("ix_telegram_fact_chat_time", "telegram_message_facts", ["chat_id", "published_at"])
    if "telegram_analytics_sources" not in tables:
        op.create_table("telegram_analytics_sources",
            sa.Column("chat_id", sa.BigInteger(), primary_key=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("coverage_since", sa.DateTime(timezone=True)),
            sa.Column("checked_at", sa.DateTime(timezone=True)),
            sa.Column("last_event_at", sa.DateTime(timezone=True)),
            sa.Column("detail", sa.String(80)))



def downgrade():
    # Observed history is durable; rolling back application code preserves it.
    raise NotImplementedError("Telegram observations must be retained; roll back application code only")
