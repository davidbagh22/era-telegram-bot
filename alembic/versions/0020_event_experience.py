"""rich event experience and creation wizard

Revision ID: 0020_event_experience
Revises: 0019_general_chat_autocontent
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0020_event_experience"
down_revision = "0019_general_chat_autocontent"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists("event_experiences"):
        return
    op.create_table(
        "event_experiences",
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("full_description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("attendance_mode", sa.String(length=24), nullable=False, server_default="offline"),
        sa.Column("organizer", sa.String(length=255), nullable=True),
        sa.Column("participant_value", sa.Text(), nullable=True),
        sa.Column("contact", sa.String(length=255), nullable=True),
        sa.Column("chat_url", sa.String(length=500), nullable=True),
        sa.Column("registration_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("registration_close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waitlist_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("registration_audience", sa.String(length=64), nullable=False, server_default="all"),
        sa.Column("program", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("participant_tasks", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("reminders", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("broadcast_targets", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("broadcast_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("wizard_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("poster_content_type", sa.String(length=100), nullable=True),
        sa.Column("poster_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    if _table_exists("event_experiences"):
        op.drop_table("event_experiences")
