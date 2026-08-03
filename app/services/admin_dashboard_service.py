from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    DepartmentApplication,
    Event,
    EventActivitySubmission,
    PortfolioItem,
    Project,
    Report,
    RewardRedemption,
    Task,
    TaskSubmission,
    User,
    UserQuestion,
)
from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus, Role, TaskStatus

ATTENTION_KEYS = (
    "users_pending",
    "projects_review",
    "events_pending",
    "task_results",
    "activity_results",
    "rewards",
    "portfolio",
    "reports",
    "questions",
    "departments",
)


def has_dashboard_access(user: User | None, settings: Settings, telegram_id: int) -> bool:
    """Mirrors app/handlers/admin/dashboard_block_a.py::_is_admin — any
    active permission grant (not just the admin role) unlocks the
    dashboard, matching the Bot's existing rule exactly."""
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (
            user
            and not user.is_blocked
            and not user.is_archived
            and any(g.is_active for g in (user.permission_grants or []))
        )
    )


async def _count(session: AsyncSession, model, *conditions) -> int:
    query = select(func.count()).select_from(model)
    for condition in conditions:
        query = query.where(condition)
    return int(await session.scalar(query) or 0)


@dataclass(frozen=True)
class DashboardMetrics:
    values: dict[str, int]
    attention_total: int


async def dashboard_metrics(session: AsyncSession) -> DashboardMetrics:
    """Mirrors app/handlers/admin/dashboard_block_a.py::_metrics exactly —
    single source of truth for both the Bot panel and the Mini App
    dashboard."""
    values = {
        "users_total": await _count(session, User, User.is_archived.is_(False)),
        "users_approved": await _count(
            session,
            User,
            User.application_status == ApplicationStatus.APPROVED,
            User.is_archived.is_(False),
        ),
        "users_pending": await _count(
            session,
            User,
            User.application_status.in_([ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]),
            User.is_archived.is_(False),
        ),
        "activists": await _count(
            session, User, User.role == Role.ACTIVIST, User.is_archived.is_(False)
        ),
        "leaders": await _count(
            session,
            User,
            User.role.in_([Role.LEADER, Role.HEAD, Role.COUNCIL, Role.ADMIN]),
            User.is_archived.is_(False),
        ),
        "projects_review": await _count(
            session,
            Project,
            Project.status.in_(
                [ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW]
            ),
        ),
        "projects_active": await _count(
            session, Project, Project.status.in_([ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS])
        ),
        "events_pending": await _count(session, Event, Event.status == EventStatus.PENDING_APPROVAL),
        "events_live": await _count(
            session,
            Event,
            Event.status.in_(
                [
                    EventStatus.APPROVED,
                    EventStatus.PUBLISHED,
                    EventStatus.REGISTRATION_OPEN,
                    EventStatus.ACTIVE,
                ]
            ),
        ),
        "tasks_open": await _count(
            session,
            Task,
            Task.status.in_([TaskStatus.NEW, TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]),
        ),
        "task_results": await _count(session, TaskSubmission, TaskSubmission.status == "pending"),
        "activity_results": await _count(
            session,
            EventActivitySubmission,
            EventActivitySubmission.status.in_(["pending", "leader_approved"]),
        ),
        "rewards": await _count(
            session, RewardRedemption, RewardRedemption.status.in_(["pending", "reserved", "answered"])
        ),
        "portfolio": await _count(session, PortfolioItem, PortfolioItem.status == "pending"),
        "reports": await _count(
            session, Report, Report.status.in_(["pending", "submitted", "needs_revision"])
        ),
        "questions": await _count(session, UserQuestion, UserQuestion.status.in_(["new", "open"])),
        "departments": await _count(
            session, DepartmentApplication, DepartmentApplication.status == "pending"
        ),
    }
    attention_total = sum(values[key] for key in ATTENTION_KEYS)
    return DashboardMetrics(values=values, attention_total=attention_total)
