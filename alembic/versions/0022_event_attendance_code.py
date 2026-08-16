"""replace QR event attendance with per-event confirmation codes

Revision ID: 0022_event_attendance_code
Revises: 0021_my_vector
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_event_attendance_code"
down_revision = "0021_my_vector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_attendance_sessions",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("attendance_code", sa.String(length=16), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_by", sa.Integer(), nullable=True),
        sa.Column("completed_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["started_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["completed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("attendance_code", name="uq_event_attendance_sessions_code"),
    )
    op.create_index(
        "ix_event_attendance_sessions_attendance_code",
        "event_attendance_sessions",
        ["attendance_code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_attendance_sessions_attendance_code",
        table_name="event_attendance_sessions",
    )
    op.drop_table("event_attendance_sessions")
