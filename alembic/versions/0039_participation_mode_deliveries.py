"""Add durable participation-mode notification deliveries.

Revision ID: 0039_participation_delivery
Revises: 0038_unify_portfolio

Tolerate fresh databases where historical 0001 has already created current
metadata, while still creating the table and indexes on older production DBs.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0039_participation_delivery"
down_revision = "0038_unify_portfolio"
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
    if not _table_exists("participation_mode_deliveries"):
        op.create_table(
            "participation_mode_deliveries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("idempotency_key", sa.String(length=200), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_participation_mode_delivery_key"),
        )
    _create_index_if_missing("ix_participation_mode_deliveries_user_id", "participation_mode_deliveries", ["user_id"])
    _create_index_if_missing("ix_participation_mode_deliveries_kind", "participation_mode_deliveries", ["kind"])
    _create_index_if_missing("ix_participation_mode_deliveries_idempotency_key", "participation_mode_deliveries", ["idempotency_key"])
    _create_index_if_missing("ix_participation_mode_deliveries_status", "participation_mode_deliveries", ["status"])
    _create_index_if_missing("ix_participation_mode_deliveries_scheduled_at", "participation_mode_deliveries", ["scheduled_at"])


def downgrade() -> None:
    if _table_exists("participation_mode_deliveries"):
        op.drop_table("participation_mode_deliveries")
