"""Add participation lifecycle, onboarding and reactivation state.

Revision ID: 0036_participation_lifecycle
Revises: 0035_merge_heads
"""

from alembic import op
import sqlalchemy as sa


revision = "0036_participation_lifecycle"
down_revision = "0035_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participation_lifecycles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("participation_mode", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("mode_before_pause", sa.String(length=16), nullable=True),
        sa.Column("activity_state", sa.String(length=24), nullable=False, server_default="ADAPTATION"),
        sa.Column("state_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_meaningful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pause_until", sa.Date(), nullable=True),
        sa.Column("mode_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("onboarding_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_participation_lifecycles_participation_mode", "participation_lifecycles", ["participation_mode"])
    op.create_index("ix_participation_lifecycles_activity_state", "participation_lifecycles", ["activity_state"])
    op.create_index("ix_participation_lifecycles_last_meaningful_at", "participation_lifecycles", ["last_meaningful_at"])
    op.create_index("ix_participation_lifecycles_pause_until", "participation_lifecycles", ["pause_until"])

    op.create_table(
        "reactivation_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("campaign_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("current_attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=True),
        sa.Column("inactivity_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_key", name="uq_reactivation_campaign_key"),
    )
    op.create_index("ix_reactivation_campaigns_user_id", "reactivation_campaigns", ["user_id"])
    op.create_index("ix_reactivation_campaigns_campaign_key", "reactivation_campaigns", ["campaign_key"])
    op.create_index("ix_reactivation_campaigns_status", "reactivation_campaigns", ["status"])
    op.create_index("ix_reactivation_campaigns_next_attempt_at", "reactivation_campaigns", ["next_attempt_at"])

    op.create_table(
        "reactivation_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["campaign_id"], ["reactivation_campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "attempt_no", name="uq_reactivation_campaign_attempt"),
        sa.UniqueConstraint("idempotency_key", name="uq_reactivation_delivery_idempotency"),
    )
    op.create_index("ix_reactivation_deliveries_campaign_id", "reactivation_deliveries", ["campaign_id"])
    op.create_index("ix_reactivation_deliveries_idempotency_key", "reactivation_deliveries", ["idempotency_key"])
    op.create_index("ix_reactivation_deliveries_status", "reactivation_deliveries", ["status"])

    # Every existing user receives one lifecycle row. Registration remains the
    # authoritative user record; this only initializes lifecycle state.
    op.execute(
        sa.text(
            """
            INSERT INTO participation_lifecycles
                (user_id, participation_mode, activity_state, state_since, onboarding_version, created_at, updated_at)
            SELECT id, 'ACTIVE', 'ADAPTATION', CURRENT_TIMESTAMP, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM users
            ON CONFLICT (user_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_reactivation_deliveries_status", table_name="reactivation_deliveries")
    op.drop_index("ix_reactivation_deliveries_idempotency_key", table_name="reactivation_deliveries")
    op.drop_index("ix_reactivation_deliveries_campaign_id", table_name="reactivation_deliveries")
    op.drop_table("reactivation_deliveries")
    op.drop_index("ix_reactivation_campaigns_next_attempt_at", table_name="reactivation_campaigns")
    op.drop_index("ix_reactivation_campaigns_status", table_name="reactivation_campaigns")
    op.drop_index("ix_reactivation_campaigns_campaign_key", table_name="reactivation_campaigns")
    op.drop_index("ix_reactivation_campaigns_user_id", table_name="reactivation_campaigns")
    op.drop_table("reactivation_campaigns")
    op.drop_index("ix_participation_lifecycles_pause_until", table_name="participation_lifecycles")
    op.drop_index("ix_participation_lifecycles_last_meaningful_at", table_name="participation_lifecycles")
    op.drop_index("ix_participation_lifecycles_activity_state", table_name="participation_lifecycles")
    op.drop_index("ix_participation_lifecycles_participation_mode", table_name="participation_lifecycles")
    op.drop_table("participation_lifecycles")
