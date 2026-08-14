"""general chat autocontent persistence

Revision ID: 0019_general_chat_autocontent
Revises: 0018_system_health
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0019_general_chat_autocontent"
down_revision = "0018_system_health"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("general_content_overrides"):
        op.create_table(
            "general_content_overrides",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("content_id", sa.String(length=100), nullable=False),
            sa.Column("override_text", sa.Text(), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_skipped", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("content_id", name="uq_general_content_overrides_content_id"),
        )
        op.create_index("ix_general_content_overrides_content_id", "general_content_overrides", ["content_id"], unique=True)

    if not _table_exists("general_content_deliveries"):
        op.create_table(
            "general_content_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("idempotency_key", sa.String(length=180), nullable=False),
            sa.Column("content_id", sa.String(length=100), nullable=False),
            sa.Column("content_type", sa.String(length=32), nullable=False),
            sa.Column("slot", sa.String(length=16), nullable=False),
            sa.Column("chat_key", sa.String(length=32), nullable=False, server_default="general"),
            sa.Column("chat_id", sa.BigInteger(), nullable=True),
            sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
            sa.Column("planned_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_code", sa.String(length=100), nullable=True),
            sa.Column("error_detail", sa.String(length=500), nullable=True),
            sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("idempotency_key", name="uq_general_content_delivery_idempotency"),
        )
        op.create_index("ix_general_content_deliveries_idempotency_key", "general_content_deliveries", ["idempotency_key"], unique=True)
        op.create_index("ix_general_content_deliveries_content_type", "general_content_deliveries", ["content_type"])
        op.create_index("ix_general_content_deliveries_status", "general_content_deliveries", ["status"])
        op.create_index("ix_general_content_delivery_planned", "general_content_deliveries", ["planned_at"])
        op.create_index("ix_general_content_delivery_content", "general_content_deliveries", ["content_id"])


def downgrade() -> None:
    if _table_exists("general_content_deliveries"):
        op.drop_table("general_content_deliveries")
    if _table_exists("general_content_overrides"):
        op.drop_table("general_content_overrides")
