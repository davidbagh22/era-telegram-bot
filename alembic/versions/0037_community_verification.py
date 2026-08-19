"""Add Community Verification campaign and durable delivery storage.

Revision ID: 0037_community_verification
Revises: 0036_participation_lifecycle
"""

from alembic import op
import sqlalchemy as sa


revision = "0037_community_verification"
down_revision = "0036_participation_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.create_index("ix_community_member_identities_user_id", "community_member_identities", ["user_id"])
    op.create_index("ix_community_member_identities_general_chat_id", "community_member_identities", ["general_chat_id"])
    op.create_index("ix_community_member_identities_last_seen_at", "community_member_identities", ["last_seen_at"])
    op.create_index("ix_community_member_identities_is_current_member", "community_member_identities", ["is_current_member"])

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
    op.create_index("ix_community_verification_campaigns_launch_key", "community_verification_campaigns", ["launch_key"])
    op.create_index("ix_community_verification_campaigns_status", "community_verification_campaigns", ["status"])
    op.create_index("ix_community_verification_campaigns_ends_at", "community_verification_campaigns", ["ends_at"])

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
    op.create_index("ix_community_verification_deliveries_campaign_id", "community_verification_deliveries", ["campaign_id"])
    op.create_index("ix_community_verification_deliveries_telegram_id", "community_verification_deliveries", ["telegram_id"])
    op.create_index("ix_community_verification_deliveries_user_id", "community_verification_deliveries", ["user_id"])
    op.create_index("ix_community_verification_deliveries_delivery_kind", "community_verification_deliveries", ["delivery_kind"])
    op.create_index("ix_community_verification_deliveries_status", "community_verification_deliveries", ["status"])
    op.create_index("ix_community_verification_deliveries_idempotency_key", "community_verification_deliveries", ["idempotency_key"])

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
    op.drop_index("ix_community_verification_deliveries_idempotency_key", table_name="community_verification_deliveries")
    op.drop_index("ix_community_verification_deliveries_status", table_name="community_verification_deliveries")
    op.drop_index("ix_community_verification_deliveries_delivery_kind", table_name="community_verification_deliveries")
    op.drop_index("ix_community_verification_deliveries_user_id", table_name="community_verification_deliveries")
    op.drop_index("ix_community_verification_deliveries_telegram_id", table_name="community_verification_deliveries")
    op.drop_index("ix_community_verification_deliveries_campaign_id", table_name="community_verification_deliveries")
    op.drop_table("community_verification_deliveries")
    op.drop_index("ix_community_verification_campaigns_ends_at", table_name="community_verification_campaigns")
    op.drop_index("ix_community_verification_campaigns_status", table_name="community_verification_campaigns")
    op.drop_index("ix_community_verification_campaigns_launch_key", table_name="community_verification_campaigns")
    op.drop_table("community_verification_campaigns")
    op.drop_index("ix_community_member_identities_is_current_member", table_name="community_member_identities")
    op.drop_index("ix_community_member_identities_last_seen_at", table_name="community_member_identities")
    op.drop_index("ix_community_member_identities_general_chat_id", table_name="community_member_identities")
    op.drop_index("ix_community_member_identities_user_id", table_name="community_member_identities")
    op.drop_table("community_member_identities")
