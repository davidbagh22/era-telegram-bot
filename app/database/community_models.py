from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class CommunityMissionTemplate(TimestampMixin, Base):
    """Reusable authored Community Mission template.

    Launching a template creates the existing ``Task`` entity. This table is
    only a reusable catalog and therefore does not become a second task engine.
    """

    __tablename__ = "community_mission_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), index=True)
    claim_mode: Mapped[str] = mapped_column(String(24), default="TEAM")
    min_people: Mapped[int] = mapped_column(Integer, default=1)
    max_people: Mapped[int] = mapped_column(Integer, default=1)
    workspace_chat_key: Mapped[str] = mapped_column(String(32))
    deadline_days: Mapped[int] = mapped_column(Integer, default=14)
    deliverable: Mapped[str] = mapped_column(Text)
    points: Mapped[int] = mapped_column(Integer, default=80)
    counts_toward: Mapped[list[str]] = mapped_column(JSON, default=list)
    repeatable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class TaskSquad(TimestampMixin, Base):
    """One shared workspace for a team working on one existing Task."""

    __tablename__ = "task_squads"
    __table_args__ = (UniqueConstraint("task_id", name="uq_task_squad_task"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_chat_key: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="forming", index=True)
    checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    topic_id: Mapped[int | None] = mapped_column(Integer)
    anchor_message_id: Mapped[int | None] = mapped_column(Integer)
    checkpoint_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overdue_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submission_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskSubtask(TimestampMixin, Base):
    """Suggested/confirmed individual responsibility inside a Task Squad."""

    __tablename__ = "task_subtasks"
    __table_args__ = (
        UniqueConstraint("squad_id", "role_key", name="uq_task_subtask_squad_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("task_squads.id", ondelete="CASCADE"), index=True)
    role_key: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24), default="proposed", index=True)
    deliverable: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
