from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    DepartmentApplication,
    Event,
    EventActivitySubmission,
    EventRegistration,
    PortfolioItem,
    Project,
    Report,
    RewardRedemption,
    Task,
    TaskSubmission,
    User,
    UserQuestion,
)
from app.services.authorization_service import is_full_admin
from app.utils.constants import (
    ApplicationStatus,
    EventStatus,
    ProjectStatus,
    RegistrationStatus,
    Role,
    TaskStatus,
)

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
    """Global Command Center access is an administrator capability.

    A delegated permission such as ``people.view`` or ``events.manage`` must
    never become a back door into organization-wide analytics, contacts,
    leadership workload, exports, or other endpoints that share the admin
    router's dashboard guard. Scoped managers use their dedicated scoped APIs.
    """
    return is_full_admin(user, settings, telegram_id)


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
    """Live Command Center counters. Every number maps to a real entity list."""
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
        "event_registrations": await _count(
            session,
            EventRegistration,
            EventRegistration.status.in_(
                [
                    RegistrationStatus.REGISTERED,
                    RegistrationStatus.WILL_COME,
                    RegistrationStatus.ATTENDED,
                ]
            ),
        ),
        "event_waitlist": await _count(
            session,
            EventRegistration,
            EventRegistration.status == RegistrationStatus.WAITLIST,
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
