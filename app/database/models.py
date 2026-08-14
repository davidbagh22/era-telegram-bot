from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.utils.constants import (
    ApplicationStatus,
    EventStatus,
    ParticipationStatus,
    ProjectStatus,
    RegistrationStatus,
    Role,
    TaskStatus,
)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    birth_date: Mapped[date | None] = mapped_column(Date, index=True)
    age: Mapped[int | None] = mapped_column(Integer)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    city: Mapped[str | None] = mapped_column(String(100))
    education_work: Mapped[str | None] = mapped_column(String(255))
    occupation: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    experience: Mapped[str | None] = mapped_column(Text)
    motivation: Mapped[str | None] = mapped_column(Text)
    available_time: Mapped[str | None] = mapped_column(String(100))
    desired_path: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(32), default=Role.PARTICIPANT)
    participation_status: Mapped[str] = mapped_column(
        String(32), default=ParticipationStatus.NEW_MEMBER
    )
    application_status: Mapped[str] = mapped_column(
        String(32), default=ApplicationStatus.PENDING, index=True
    )
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_channel_subscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    personal_data_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # One-time migration flag: True means this user's Telegram client has
    # never had (or has already had cleared) the old persistent
    # ReplyKeyboardMarkup main menu (removed — see
    # app/middlewares/legacy_keyboard_cleanup.py). `default=True` here is
    # the client-side (ORM-insert) default, so every user created *after*
    # this migration ships starts already "clean" and is never sent the
    # one-time ReplyKeyboardRemove notice. Existing rows are backfilled to
    # False by migration 0016, since Telegram keeps a persistent reply
    # keyboard visible on the client until the bot explicitly removes it —
    # they may still have one cached from weeks ago.
    legacy_reply_keyboard_removed: Mapped[bool] = mapped_column(Boolean, default=True)

    departments: Mapped[list[UserDepartment]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    directions: Mapped[list[UserDirection]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    permission_grants: Mapped[list[PermissionGrant]] = relationship(
        foreign_keys="PermissionGrant.user_id", lazy="selectin"
    )


class Department(TimestampMixin, Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    chat_url: Mapped[str | None] = mapped_column(String(255))
    leader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    directions: Mapped[list[Direction]] = relationship(
        back_populates="department", cascade="all, delete-orphan", lazy="selectin"
    )


class Direction(TimestampMixin, Base):
    __tablename__ = "directions"
    __table_args__ = (UniqueConstraint("department_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    leader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    department: Mapped[Department] = relationship(back_populates="directions")


class UserDepartment(TimestampMixin, Base):
    __tablename__ = "user_departments"
    __table_args__ = (UniqueConstraint("user_id", "department_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(32), default="interested")

    user: Mapped[User] = relationship(back_populates="departments")
    department: Mapped[Department] = relationship(lazy="joined")


class UserDirection(TimestampMixin, Base):
    __tablename__ = "user_directions"
    __table_args__ = (UniqueConstraint("user_id", "direction_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    direction_id: Mapped[int] = mapped_column(
        ForeignKey("directions.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(32), default="interested")

    user: Mapped[User] = relationship(back_populates="directions")
    direction: Mapped[Direction] = relationship(lazy="joined")


class DepartmentApplication(TimestampMixin, Base):
    __tablename__ = "department_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    direction_id: Mapped[int | None] = mapped_column(ForeignKey("directions.id"))
    motivation: Mapped[str] = mapped_column(Text)
    usefulness: Mapped[str] = mapped_column(Text)
    available_time: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    admin_comment: Mapped[str | None] = mapped_column(Text)


class ConsentLog(TimestampMixin, Base):
    """Technical foundation for consent auditability — see
    docs/DATA_INVENTORY.md section 5. `User.personal_data_consent` stays a
    bare bool (still the field actually checked anywhere), this table adds
    a real audit trail alongside it: which consent, what policy text
    version, when, granted or withdrawn. `policy_version` is a plain
    string placeholder (see app.services.consent_service) until the
    platform owner supplies real policy text — this table records consent
    *events*, it does not itself define or validate policy content, which
    is explicitly not a decision a technical PR can make unilaterally."""

    __tablename__ = "consent_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    consent_type: Mapped[str] = mapped_column(String(64), index=True)
    policy_version: Mapped[str] = mapped_column(String(32))
    granted: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(16))


class DataDeletionRequest(TimestampMixin, Base):
    """Self-service "right to erasure" request (see
    docs/DATA_INVENTORY.md section 4, docs/FINAL_PRODUCTION_ACCEPTANCE.md
    item #118). A participant requesting deletion doesn't trigger an
    instant hard-delete — the platform's own PointTransaction ledger is
    explicitly financial-record-like and retained (docs/DATA_INVENTORY.md
    section 2), and a real hard-delete would break referential integrity
    across projects/tasks/audit trail this user authored or is referenced
    by. Instead this is a request → admin-reviewed anonymization: the
    request is recorded and audited immediately (so it can never be
    silently lost), and app.services.data_rights_service.fulfill_request()
    clears PII fields while keeping the row (and everything that
    references it) intact — the same "archive, don't delete" pattern
    already used for User.is_archived elsewhere in this app."""

    __tablename__ = "data_deletion_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    note: Mapped[str | None] = mapped_column(Text)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulfilled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Event(TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_status_date", "status", "event_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    event_date: Mapped[date] = mapped_column(Date)
    event_time: Mapped[time] = mapped_column(Time)
    location: Mapped[str] = mapped_column(String(255))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    direction_id: Mapped[int | None] = mapped_column(ForeignKey("directions.id"))
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), index=True
    )
    format: Mapped[str] = mapped_column(String(100))
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    participant_limit: Mapped[int | None] = mapped_column(Integer)
    access_type: Mapped[str] = mapped_column(String(50), default="all")
    needs_volunteers: Mapped[bool] = mapped_column(Boolean, default=False)
    points_for_visit: Mapped[int] = mapped_column(Integer, default=5)
    selfie_required: Mapped[bool] = mapped_column(Boolean, default=True)
    poster_file_id: Mapped[str | None] = mapped_column(String(255))
    additional_info: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32), default=EventStatus.DRAFT, index=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class EventRegistration(TimestampMixin, Base):
    __tablename__ = "event_registrations"
    __table_args__ = (UniqueConstraint("event_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=RegistrationStatus.REGISTERED
    )
    last_confirmation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    reminder_stage: Mapped[int] = mapped_column(Integer, default=0)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttendanceProof(TimestampMixin, Base):
    __tablename__ = "attendance_proofs"
    __table_args__ = (UniqueConstraint("event_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    photo_file_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    admin_comment: Mapped[str | None] = mapped_column(Text)


class Feedback(TimestampMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("event_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer)
    liked: Mapped[str] = mapped_column(Text)
    improve: Mapped[str] = mapped_column(Text)
    wants_again: Mapped[str] = mapped_column(String(32))


class PointTransaction(Base):
    __tablename__ = "points"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_points_idempotency_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    points: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str | None] = mapped_column(String(64), index=True)
    source_id: Mapped[int | None] = mapped_column(Integer, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    related_event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"))
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    related_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now().astimezone()
    )


class Badge(TimestampMixin, Base):
    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class UserBadge(Base):
    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    badge_id: Mapped[int] = mapped_column(ForeignKey("badges.id"))
    reason: Mapped[str] = mapped_column(Text)
    awarded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    related_event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"))
    related_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now().astimezone()
    )


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    item_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(500))
    related_event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"))
    related_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="verified", index=True)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    admin_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now().astimezone()
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    direction_id: Mapped[int | None] = mapped_column(ForeignKey("directions.id"))
    title: Mapped[str] = mapped_column(String(255))
    short_description: Mapped[str] = mapped_column(Text)
    relevance: Mapped[str | None] = mapped_column(Text)
    goal: Mapped[str | None] = mapped_column(Text)
    tasks: Mapped[str | None] = mapped_column(Text)
    target_audience: Mapped[str | None] = mapped_column(Text)
    format: Mapped[str | None] = mapped_column(String(100))
    program: Mapped[str | None] = mapped_column(Text)
    resources: Mapped[str | None] = mapped_column(Text)
    team: Mapped[str | None] = mapped_column(Text)
    expected_result: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[str | None] = mapped_column(Text)
    needs_from_era: Mapped[str | None] = mapped_column(Text)
    generated_document: Mapped[str | None] = mapped_column(Text)
    form_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    venue_status: Mapped[str] = mapped_column(String(32), default="not_requested")
    venue_comment: Mapped[str | None] = mapped_column(Text)
    venue_reminder_count: Mapped[int] = mapped_column(Integer, default=0)
    venue_remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proposed_date: Mapped[date | None] = mapped_column(Date)
    proposed_time: Mapped[time | None] = mapped_column(Time)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32), default=ProjectStatus.DRAFT, index=True
    )
    admin_comment: Mapped[str | None] = mapped_column(Text)

    roles: Mapped[list[ProjectRole]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    members: Mapped[list[ProjectMember]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    milestones: Mapped[list[ProjectMilestone]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )


class ProjectRole(TimestampMixin, Base):
    __tablename__ = "project_roles"
    __table_args__ = (
        UniqueConstraint("project_id", "title", name="uq_project_roles_project_title"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    capacity: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)

    project: Mapped[Project] = relationship(back_populates="roles")
    members: Mapped[list[ProjectMember]] = relationship(back_populates="role")


class ProjectMember(TimestampMixin, Base):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("project_roles.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    application_text: Mapped[str | None] = mapped_column(Text)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    contribution_status: Mapped[str] = mapped_column(
        String(32), default="unconfirmed", index=True
    )
    contribution_summary: Mapped[str | None] = mapped_column(Text)
    contribution_role_title: Mapped[str | None] = mapped_column(String(120))
    contribution_result: Mapped[str | None] = mapped_column(Text)
    contribution_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contribution_confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    project: Mapped[Project] = relationship(back_populates="members")
    role: Mapped[ProjectRole | None] = relationship(back_populates="members")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class ProjectMilestone(TimestampMixin, Base):
    __tablename__ = "project_milestones"
    __table_args__ = (
        UniqueConstraint("project_id", "sort_order", name="uq_project_milestones_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    project: Mapped[Project] = relationship(back_populates="milestones")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    direction_id: Mapped[int | None] = mapped_column(ForeignKey("directions.id"))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    points: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.NEW, index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[str | None] = mapped_column(String(255))
    task_type: Mapped[str] = mapped_column(String(32), default="private", index=True)
    audience_filter_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reward_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    chat_url: Mapped[str | None] = mapped_column(String(500))
    max_participants: Mapped[int | None] = mapped_column(Integer)
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)


class TaskDelivery(TimestampMixin, Base):
    """One row per chat a task announcement was dispatched to (2026-08
    master spec section 33) -- entity<->chat<->message_id<->status<->error
    tracking, generic enough to extend to other entity types later but not
    built out further than tasks need today. Task creation itself must
    never roll back because a Telegram send failed (see
    app/services/leader_service.py::create_open_task()) -- a failed
    delivery is recorded here, not raised, so an admin/leader can see
    "created but not delivered to X" and retry that one destination."""

    __tablename__ = "task_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    chat_key: Mapped[str] = mapped_column(String(32))
    chat_id: Mapped[int] = mapped_column(BigInteger)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="failed", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_type: Mapped[str] = mapped_column(String(50))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    direction_id: Mapped[int | None] = mapped_column(ForeignKey("directions.id"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"))
    month: Mapped[str | None] = mapped_column(String(7))
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    file_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)


class UserQuestion(TimestampMixin, Base):
    __tablename__ = "user_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    file_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    admin_answer: Mapped[str | None] = mapped_column(Text)
    answered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Broadcast(TimestampMixin, Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    audience_type: Mapped[str] = mapped_column(String(50))
    audience_filter_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    photo_file_id: Mapped[str | None] = mapped_column(String(255))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now().astimezone(), index=True
    )


class Proposal(TimestampMixin, Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    proposer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    proposal_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    admin_comment: Mapped[str | None] = mapped_column(Text)


class AppSetting(TimestampMixin, Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Office(TimestampMixin, Base):
    __tablename__ = "offices"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    scope_type: Mapped[str] = mapped_column(String(32), default="community")
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    direction_id: Mapped[int | None] = mapped_column(ForeignKey("directions.id"))
    public_contact: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class UserOffice(TimestampMixin, Base):
    __tablename__ = "user_offices"
    __table_args__ = (UniqueConstraint("user_id", "office_id", "starts_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id"), index=True)
    appointed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    starts_at: Mapped[date] = mapped_column(Date, default=date.today)
    ends_at: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class PermissionGrant(TimestampMixin, Base):
    __tablename__ = "permission_grants"
    __table_args__ = (
        UniqueConstraint("user_id", "permission", "scope_type", "scope_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    permission: Mapped[str] = mapped_column(String(100), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="global")
    scope_id: Mapped[int] = mapped_column(Integer, default=0)
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class ChatGreeting(TimestampMixin, Base):
    __tablename__ = "chat_greetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_key: Mapped[str] = mapped_column(String(50), unique=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(150))
    text: Mapped[str] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class EventActivity(TimestampMixin, Base):
    __tablename__ = "event_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    submission_type: Mapped[str] = mapped_column(String(32), default="text")
    points: Mapped[int] = mapped_column(Integer, default=0)
    badge_id: Mapped[int | None] = mapped_column(ForeignKey("badges.id"))
    certificate_title: Mapped[str | None] = mapped_column(String(255))
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class EventActivitySubmission(TimestampMixin, Base):
    __tablename__ = "event_activity_submissions"
    __table_args__ = (UniqueConstraint("activity_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("event_activities.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[str | None] = mapped_column(String(255))
    file_type: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    admin_comment: Mapped[str | None] = mapped_column(Text)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0)


class TaskParticipant(TimestampMixin, Base):
    __tablename__ = "task_participants"
    __table_args__ = (UniqueConstraint("task_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="joined", index=True)


class TaskSubmission(TimestampMixin, Base):
    __tablename__ = "task_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[str | None] = mapped_column(String(255))
    collaborators_json: Mapped[list[int]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    admin_comment: Mapped[str | None] = mapped_column(Text)


class RewardItem(TimestampMixin, Base):
    __tablename__ = "reward_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    point_cost: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int | None] = mapped_column(Integer)
    image_file_id: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class RewardRedemption(TimestampMixin, Base):
    __tablename__ = "reward_redemptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    reward_id: Mapped[int] = mapped_column(ForeignKey("reward_items.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    points_spent: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    admin_comment: Mapped[str | None] = mapped_column(Text)


class Auction(TimestampMixin, Base):
    __tablename__ = "auctions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    audience_filter_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    minimum_bid: Mapped[int] = mapped_column(Integer, default=1)
    bid_step: Mapped[int] = mapped_column(Integer, default=1)
    winner_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class AuctionBid(TimestampMixin, Base):
    __tablename__ = "auction_bids"
    __table_args__ = (UniqueConstraint("auction_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    auction_id: Mapped[int] = mapped_column(ForeignKey("auctions.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    selected_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
