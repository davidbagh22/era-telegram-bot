"""Add Weekly Leadership Pulse snapshot and feedback persistence.

Revision ID: 0041_leadership_weekly_loop
Revises: 0040_notification_delivery
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0041_leadership_weekly_loop"
down_revision = "0040_notification_delivery"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("leadership_report_pulses"):
        op.create_table(
            "leadership_report_pulses",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("report_id", sa.Integer(), nullable=False),
            sa.Column("system_snapshot", sa.JSON(), nullable=False),
            sa.Column("pace_score", sa.Integer(), nullable=True),
            sa.Column("clarity_score", sa.Integer(), nullable=True),
            sa.Column("load_score", sa.Integer(), nullable=True),
            sa.Column("attention_text", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["report_id"], ["leadership_reports.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("report_id", name="uq_leadership_report_pulses_report"),
        )
        op.create_index(
            "ix_leadership_report_pulses_report_id",
            "leadership_report_pulses",
            ["report_id"],
        )

    if not _table_exists("leadership_feedback"):
        op.create_table(
            "leadership_feedback",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("report_id", sa.Integer(), nullable=False),
            sa.Column("reviewer_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="acknowledged"),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["report_id"], ["leadership_reports.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_leadership_feedback_report_id", "leadership_feedback", ["report_id"])
        op.create_index("ix_leadership_feedback_reviewer_id", "leadership_feedback", ["reviewer_id"])
        op.create_index("ix_leadership_feedback_status", "leadership_feedback", ["status"])


def downgrade() -> None:
    if _table_exists("leadership_feedback"):
        op.drop_table("leadership_feedback")
    if _table_exists("leadership_report_pulses"):
        op.drop_table("leadership_report_pulses")
