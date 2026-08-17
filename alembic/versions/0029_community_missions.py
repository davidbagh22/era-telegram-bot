"""Community Missions and Task Squad support.

Revision ID: 0029_community_missions
Revises: 0028_recognition_opportunities
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0029_community_missions"
down_revision = "0028_recognition_opportunities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "community_mission_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("claim_mode", sa.String(length=24), nullable=False, server_default="TEAM"),
        sa.Column("min_people", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_people", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("workspace_chat_key", sa.String(length=32), nullable=False),
        sa.Column("deadline_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("deliverable", sa.Text(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("counts_toward", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("repeatable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_community_mission_templates_code", "community_mission_templates", ["code"])
    op.create_index("ix_community_mission_templates_month", "community_mission_templates", ["month"])
    op.create_index("ix_community_mission_templates_category", "community_mission_templates", ["category"])
    op.create_index("ix_community_mission_templates_is_active", "community_mission_templates", ["is_active"])

    op.create_table(
        "task_squads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("responsible_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("workspace_chat_key", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="forming"),
        sa.Column("checkpoint_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.Column("anchor_message_id", sa.Integer(), nullable=True),
        sa.Column("checkpoint_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overdue_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submission_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", name="uq_task_squad_task"),
    )
    op.create_index("ix_task_squads_task_id", "task_squads", ["task_id"])
    op.create_index("ix_task_squads_responsible_user_id", "task_squads", ["responsible_user_id"])
    op.create_index("ix_task_squads_workspace_chat_key", "task_squads", ["workspace_chat_key"])
    op.create_index("ix_task_squads_status", "task_squads", ["status"])
    op.create_index("ix_task_squads_checkpoint_at", "task_squads", ["checkpoint_at"])

    op.create_table(
        "task_subtasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("squad_id", sa.Integer(), sa.ForeignKey("task_squads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_key", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="proposed"),
        sa.Column("deliverable", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("squad_id", "role_key", name="uq_task_subtask_squad_role"),
    )
    op.create_index("ix_task_subtasks_squad_id", "task_subtasks", ["squad_id"])
    op.create_index("ix_task_subtasks_assignee_id", "task_subtasks", ["assignee_id"])
    op.create_index("ix_task_subtasks_deadline", "task_subtasks", ["deadline"])
    op.create_index("ix_task_subtasks_status", "task_subtasks", ["status"])


def downgrade() -> None:
    op.drop_table("task_subtasks")
    op.drop_table("task_squads")
    op.drop_table("community_mission_templates")
