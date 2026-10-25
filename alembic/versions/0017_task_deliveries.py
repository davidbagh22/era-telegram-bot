"""Add task_deliveries table — entity<->chat<->message_id<->status<->error
tracking for task-to-chat dispatch (2026-08 master spec section 33).
Additive only.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_task_deliveries"
down_revision = "0016_legacy_reply_keyboard_flag"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists("task_deliveries"):
        return
    op.create_table(
        "task_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("chat_key", sa.String(length=32), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="failed"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_task_deliveries_task_id", "task_deliveries", ["task_id"])
    op.create_index("ix_task_deliveries_status", "task_deliveries", ["status"])


def downgrade() -> None:
    if not _table_exists("task_deliveries"):
        return
    op.drop_index("ix_task_deliveries_status", table_name="task_deliveries")
    op.drop_index("ix_task_deliveries_task_id", table_name="task_deliveries")
    op.drop_table("task_deliveries")
