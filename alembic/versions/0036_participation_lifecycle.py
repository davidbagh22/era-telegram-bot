"""Add participation lifecycle, onboarding and reactivation state.

Revision ID: 0036_participation_lifecycle
Revises: 0035_merge_heads

The historical 0001 migration calls the *current* Base.metadata.create_all().
On a clean database that means tables introduced by later application models
may already exist before Alembic reaches this revision. Production databases
created by older releases still need the normal CREATE path, so every table and
index is created only when missing.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0036_participation_lifecycle"
down_revision = "0035_merge_heads"
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
    if not _table_exists("participation_lifecycles"):
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
    _create_index_if_missing("ix_participation_lifecycles_participation_mode", "participation_lifecycles", ["participation_mode"])
    _create_index_if_missing("ix_participation_lifecycles_activity_state", "participation_lifecycles", ["activity_state"])
    _create_index_if_missing("ix_participation_lifecycles_last_meaningful_at", "participation_lifecycles", ["last_meaningful_at"])
    _create_index_if_missing("ix_participation_lifecycles_pause_until", "participation_lifecycles", ["pause_until"])

    if not _table_exists("reactivation_campaigns"):
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
    _create_index_if_missing("ix_reactivation_campaigns_user_id", "reactivation_campaigns", ["user_id"])
    _create_index_if_missing("ix_reactivation_campaigns_campaign_key", "reactivation_campaigns", ["campaign_key"])
    _create_index_if_missing("ix_reactivation_campaigns_status", "reactivation_campaigns", ["status"])
    _create_index_if_missing("ix_reactivation_campaigns_next_attempt_at", "reactivation_campaigns", ["next_attempt_at"])

    if not _table_exists("reactivation_deliveries"):
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
    _create_index_if_missing("ix_reactivation_deliveries_campaign_id", "reactivation_deliveries", ["campaign_id"])
    _create_index_if_missing("ix_reactivation_deliveries_idempotency_key", "reactivation_deliveries", ["idempotency_key"])
    _create_index_if_missing("ix_reactivation_deliveries_status", "reactivation_deliveries", ["status"])

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
    for table_name in ("reactivation_deliveries", "reactivation_campaigns", "participation_lifecycles"):
        if _table_exists(table_name):
            op.drop_table(table_name)
