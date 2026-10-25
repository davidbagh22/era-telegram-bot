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


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # event_attendance_sessions is also a declarative model on Base.metadata,
    # so 0001's Base.metadata.create_all() (reflecting whatever models.py
    # currently defines, not a historical snapshot) already creates it on a
    # from-scratch upgrade -- guard so this migration stays a no-op for it
    # instead of erroring "already exists" (see 0023, 0024 for the same fix).
    if _table_exists("event_attendance_sessions"):
        return
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
    if not _table_exists("event_attendance_sessions"):
        return
    op.drop_index(
        "ix_event_attendance_sessions_attendance_code",
        table_name="event_attendance_sessions",
    )
    op.drop_table("event_attendance_sessions")
