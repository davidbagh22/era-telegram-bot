"""Add durable generic notification delivery ledger.

Revision ID: 0040_notification_delivery
Revises: 0039_participation_delivery

The migration tolerates fresh databases where historical 0001 may already have
created current metadata, while still upgrading older production databases.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0040_notification_delivery"
down_revision = "0039_participation_delivery"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index.get("name")
    }


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns)


def upgrade() -> None:
    if not _table_exists("notification_deliveries"):
        op.create_table(
            "notification_deliveries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("delivery_key", sa.String(length=200), nullable=False),
            sa.Column("chat_id", sa.BigInteger(), nullable=False),
            sa.Column("notification_type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_code", sa.String(length=96), nullable=True),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("delivery_key", name="uq_notification_deliveries_key"),
        )
    _create_index_if_missing(
        "ix_notification_deliveries_delivery_key",
        "notification_deliveries",
        ["delivery_key"],
    )
    _create_index_if_missing(
        "ix_notification_deliveries_chat_id",
        "notification_deliveries",
        ["chat_id"],
    )
    _create_index_if_missing(
        "ix_notification_deliveries_notification_type",
        "notification_deliveries",
        ["notification_type"],
    )
    _create_index_if_missing(
        "ix_notification_deliveries_status",
        "notification_deliveries",
        ["status"],
    )


def downgrade() -> None:
    if _table_exists("notification_deliveries"):
        op.drop_table("notification_deliveries")
