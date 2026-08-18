"""Community verification campaign + per-recipient delivery tracking.

Community Verification ToR §7/§11/§59: an admin-run "first wave" grace
period for existing chat members, plus idempotent per-recipient delivery
status for the launch/reminder DMs.

Revision ID: 0036_community_verification
Revises: 0035_merge_heads

Idempotent like 0030-0034: 0001_initial calls the current
Base.metadata.create_all(), so a fresh database may already have these
tables (and their indexes) by the time this revision runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_community_verification"
down_revision = "0035_merge_heads"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name) if index.get("name")}


def _timestamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))


def upgrade() -> None:
    if not _table_exists("community_verification_campaigns"):
        op.create_table(
            "community_verification_campaigns",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="not_started"),
            sa.Column("window_hours", sa.Integer(), nullable=False, server_default="72"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            _timestamp("created_at"),
            _timestamp("updated_at"),
        )
    campaign_indexes = _index_names("community_verification_campaigns")
    if "ix_community_verification_campaigns_status" not in campaign_indexes:
        op.create_index(
            "ix_community_verification_campaigns_status",
            "community_verification_campaigns",
            ["status"],
        )
    if "ix_community_verification_campaigns_ends_at" not in campaign_indexes:
        op.create_index(
            "ix_community_verification_campaigns_ends_at",
            "community_verification_campaigns",
            ["ends_at"],
        )

    if not _table_exists("community_verification_deliveries"):
        op.create_table(
            "community_verification_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "campaign_id",
                sa.Integer(),
                sa.ForeignKey("community_verification_campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("telegram_id", sa.BigInteger(), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
            _timestamp("created_at"),
            _timestamp("updated_at"),
            sa.UniqueConstraint("campaign_id", "telegram_id", "kind", name="uq_community_verification_delivery"),
        )
    delivery_indexes = _index_names("community_verification_deliveries")
    for column in ("campaign_id", "telegram_id", "kind", "status"):
        index_name = f"ix_community_verification_deliveries_{column}"
        if index_name not in delivery_indexes:
            op.create_index(index_name, "community_verification_deliveries", [column])


def downgrade() -> None:
    delivery_indexes = _index_names("community_verification_deliveries")
    for column in ("campaign_id", "telegram_id", "kind", "status"):
        index_name = f"ix_community_verification_deliveries_{column}"
        if index_name in delivery_indexes:
            op.drop_index(index_name, table_name="community_verification_deliveries")
    if _table_exists("community_verification_deliveries"):
        op.drop_table("community_verification_deliveries")

    campaign_indexes = _index_names("community_verification_campaigns")
    if "ix_community_verification_campaigns_ends_at" in campaign_indexes:
        op.drop_index("ix_community_verification_campaigns_ends_at", table_name="community_verification_campaigns")
    if "ix_community_verification_campaigns_status" in campaign_indexes:
        op.drop_index("ix_community_verification_campaigns_status", table_name="community_verification_campaigns")
    if _table_exists("community_verification_campaigns"):
        op.drop_table("community_verification_campaigns")
