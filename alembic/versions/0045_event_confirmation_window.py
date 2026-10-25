"""Separate event completion from attendance confirmation closing.

Revision ID: 0045_confirmation_window
Revises: 0044_era_pro
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0045_confirmation_window"
down_revision = "0044_era_pro"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("event_attendance_sessions")}
    if "confirmation_closed_at" not in columns:
        op.add_column(
            "event_attendance_sessions",
            sa.Column("confirmation_closed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("event_attendance_sessions")}
    if "confirmation_closed_at" in columns:
        op.drop_column("event_attendance_sessions", "confirmation_closed_at")
