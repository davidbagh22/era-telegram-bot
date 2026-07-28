"""Add pending chat join requests."""

import sqlalchemy as sa
from alembic import op

revision = "0011_pending_chat_join_requests"
down_revision = "0010_merge_surveys_and_points_heads"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists("pending_chat_join_requests"):
        return

    op.create_table(
        "pending_chat_join_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_key", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("chat_id", "user_id"),
    )
    op.create_index("ix_pending_chat_join_requests_chat_id", "pending_chat_join_requests", ["chat_id"])
    op.create_index("ix_pending_chat_join_requests_user_id", "pending_chat_join_requests", ["user_id"])
    op.create_index("ix_pending_chat_join_requests_chat_key", "pending_chat_join_requests", ["chat_key"])
    op.create_index("ix_pending_chat_join_requests_status", "pending_chat_join_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pending_chat_join_requests_status", table_name="pending_chat_join_requests")
    op.drop_index("ix_pending_chat_join_requests_chat_key", table_name="pending_chat_join_requests")
    op.drop_index("ix_pending_chat_join_requests_user_id", table_name="pending_chat_join_requests")
    op.drop_index("ix_pending_chat_join_requests_chat_id", table_name="pending_chat_join_requests")
    op.drop_table("pending_chat_join_requests")
