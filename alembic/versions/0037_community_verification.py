"""Add Community Verification campaign and durable delivery storage.

Revision ID: 0037_community_verification
Revises: 0036_participation_lifecycle

The repository's historical 0001 migration creates the current SQLAlchemy
metadata on fresh databases. Guard later CREATE operations so both fresh CI
installs and older production databases upgrade through the same revision.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0037_community_verification"
down_revision = "0036_participation_lifecycle"
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
    if not _table_exists("community_member_identities"):
        op.create_table(
            "community_member_identities",
            sa.Column("telegram_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("general_chat_id", sa.BigInteger(), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("is_current_member", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("retained_by_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("telegram_id"),
            sa.UniqueConstraint("user_id"),
        )
    _create_index_if_missing("ix_community_member_identities_user_id", "community_member_identities", ["user_id"])
    _create_index_if_missing("ix_community_member_identities_general_chat_id", "community_member_identities", ["general_chat_id"])
    _create_index_if_missing("ix_community_member_identities_last_seen_at", "community_member_identities", ["last_seen_at"])
    _create_index_if_missing("ix_community_member_identities_is_current_member", "community_member_identities", ["is_current_member"])

    if not _table_exists("community_verification_campaigns"):
        op.create_table(
            "community_verification_campaigns",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("launch_key", sa.String(length=160), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("duration_hours", sa.Integer(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("group_message_id", sa.BigInteger(), nullable=True),
            sa.Column("group_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("launch_key", name="uq_community_verification_launch_key"),
        )
    _create_index_if_missing("ix_community_verification_campaigns_launch_key", "community_verification_campaigns", ["launch_key"])
    _create_index_if_missing("ix_community_verification_campaigns_status", "community_verification_campaigns", ["status"])
    _create_index_if_missing("ix_community_verification_campaigns_ends_at", "community_verification_campaigns", ["ends_at"])

    if not _table_exists("community_verification_deliveries"):
        op.create_table(
            "community_verification_deliveries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("campaign_id", sa.Integer(), nullable=False),
            sa.Column("telegram_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("delivery_kind", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("idempotency_key", sa.String(length=200), nullable=False),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["campaign_id"], ["community_verification_campaigns.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_community_verification_delivery_key"),
        )
    _create_index_if_missing("ix_community_verification_deliveries_campaign_id", "community_verification_deliveries", ["campaign_id"])
    _create_index_if_missing("ix_community_verification_deliveries_telegram_id", "community_verification_deliveries", ["telegram_id"])
    _create_index_if_missing("ix_community_verification_deliveries_user_id", "community_verification_deliveries", ["user_id"])
    _create_index_if_missing("ix_community_verification_deliveries_delivery_kind", "community_verification_deliveries", ["delivery_kind"])
    _create_index_if_missing("ix_community_verification_deliveries_status", "community_verification_deliveries", ["status"])
    _create_index_if_missing("ix_community_verification_deliveries_idempotency_key", "community_verification_deliveries", ["idempotency_key"])

    # Existing User rows are known identities; future unregistered members are
    # recorded from managed-chat updates/join requests.
    op.execute(
        sa.text(
            """
            INSERT INTO community_member_identities
                (telegram_id, user_id, first_seen_at, last_seen_at, is_current_member, retained_by_admin, created_at, updated_at)
            SELECT telegram_id, id, created_at, CURRENT_TIMESTAMP, TRUE, FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM users
            ON CONFLICT (telegram_id) DO UPDATE SET user_id = EXCLUDED.user_id
            """
        )
    )


def downgrade() -> None:
    for table_name in (
        "community_verification_deliveries",
        "community_verification_campaigns",
        "community_member_identities",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
