"""Add durable participation-mode notification deliveries.

Revision ID: 0039_participation_mode_deliveries
Revises: 0038_unify_portfolio
"""

from alembic import op
import sqlalchemy as sa


revision = "0039_participation_mode_deliveries"
down_revision = "0038_unify_portfolio"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.create_index("ix_participation_mode_deliveries_user_id", "participation_mode_deliveries", ["user_id"])
    op.create_index("ix_participation_mode_deliveries_kind", "participation_mode_deliveries", ["kind"])
    op.create_index("ix_participation_mode_deliveries_idempotency_key", "participation_mode_deliveries", ["idempotency_key"])
    op.create_index("ix_participation_mode_deliveries_status", "participation_mode_deliveries", ["status"])
    op.create_index("ix_participation_mode_deliveries_scheduled_at", "participation_mode_deliveries", ["scheduled_at"])


def downgrade() -> None:
    op.drop_index("ix_participation_mode_deliveries_scheduled_at", table_name="participation_mode_deliveries")
    op.drop_index("ix_participation_mode_deliveries_status", table_name="participation_mode_deliveries")
    op.drop_index("ix_participation_mode_deliveries_idempotency_key", table_name="participation_mode_deliveries")
    op.drop_index("ix_participation_mode_deliveries_kind", table_name="participation_mode_deliveries")
    op.drop_index("ix_participation_mode_deliveries_user_id", table_name="participation_mode_deliveries")
    op.drop_table("participation_mode_deliveries")
