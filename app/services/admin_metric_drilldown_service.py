from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Event,
    EventRegistration,
    Project,
    Task,
    TaskSubmission,
    User,
)
from app.database.participation_models import ParticipationLifecycle
from app.services.meaningful_activity_service import meaningful_user_ids_since
from app.services.participation_lifecycle_service import MODE_ACTIVE, MODE_EXITED, MODE_LIGHT
from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus, RegistrationStatus

AdminMetricKey = Literal[
    "current_roster",
    "active_base",
    "projects_active",
    "events_live",
    "event_registrations",
    "task_results",
]

METRIC_LABELS: dict[str, str] = {
    "current_roster": "Текущий состав",
    "active_base": "Активная база",
    "projects_active": "Активные проекты",
    "events_live": "Активные события",
    "event_registrations": "Регистрации на события",
    "task_results": "Результаты заданий на проверке",
}


@dataclass(frozen=True, slots=True)
class MetricDrilldownRow:
    id: int
    entity_type: str
    entity_id: int
    title: str
    subtitle: str | None
    status: str | None


@dataclass(frozen=True, slots=True)
class MetricDrilldown:
    metric: str
    label: str
    rows: list[MetricDrilldownRow]

    @property
    def total(self) -> int:
        return len(self.rows)


def _value(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        value = value.value
    text = str(value).strip()
    return text or None


def _full_name(user: User) -> str:
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or f"Участник #{user.id}"


def _roster_conditions():
    return (
        User.application_status == ApplicationStatus.APPROVED,
        User.is_archived.is_(False),
        User.is_blocked.is_(False),
        or_(
            ParticipationLifecycle.user_id.is_(None),
            ParticipationLifecycle.participation_mode != MODE_EXITED,
        ),
    )


async def _current_roster(session: AsyncSession) -> list[MetricDrilldownRow]:
    users = list(
        (
            await session.scalars(
                select(User)
                .outerjoin(ParticipationLifecycle, ParticipationLifecycle.user_id == User.id)
                .where(*_roster_conditions())
                .order_by(User.first_name, User.last_name, User.id)
            )
        ).unique().all()
    )
    return [
        MetricDrilldownRow(
            id=user.id,
            entity_type="user",
            entity_id=user.id,
            title=_full_name(user),
            subtitle=" · ".join(
                item for item in (_value(user.participation_status), _value(user.role), user.city) if item
            )
            or None,
            status=_value(user.application_status),
        )
        for user in users
    ]


async def _active_base(session: AsyncSession) -> list[MetricDrilldownRow]:
    active_ids = await meaningful_user_ids_since(
        session,
        datetime.now(timezone.utc) - timedelta(days=14),
        include_current_responsibility=True,
    )
    if not active_ids:
        return []
    users = list(
        (
            await session.scalars(
                select(User)
                .outerjoin(ParticipationLifecycle, ParticipationLifecycle.user_id == User.id)
                .where(
                    User.application_status == ApplicationStatus.APPROVED,
                    User.is_archived.is_(False),
                    User.is_blocked.is_(False),
                    User.id.in_(active_ids),
                    or_(
                        ParticipationLifecycle.user_id.is_(None),
                        ParticipationLifecycle.participation_mode.in_([MODE_ACTIVE, MODE_LIGHT]),
                    ),
                )
                .order_by(User.first_name, User.last_name, User.id)
            )
        ).unique().all()
    )
    return [
        MetricDrilldownRow(
            id=user.id,
            entity_type="user",
            entity_id=user.id,
            title=_full_name(user),
            subtitle="Meaningful Activity · 14 дней",
            status=_value(user.participation_status),
        )
        for user in users
    ]


async def _projects_active(session: AsyncSession) -> list[MetricDrilldownRow]:
    projects = list(
        (
            await session.scalars(
                select(Project)
                .where(Project.status.in_([ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS]))
                .order_by(Project.created_at.desc(), Project.id.desc())
            )
        ).all()
    )
    return [
        MetricDrilldownRow(
            id=project.id,
            entity_type="project",
            entity_id=project.id,
            title=project.title,
            subtitle=project.created_at.date().isoformat() if project.created_at else None,
            status=_value(project.status),
        )
        for project in projects
    ]


async def _events_live(session: AsyncSession) -> list[MetricDrilldownRow]:
    events = list(
        (
            await session.scalars(
                select(Event)
                .where(
                    Event.status.in_(
                        [
                            EventStatus.APPROVED,
                            EventStatus.PUBLISHED,
                            EventStatus.REGISTRATION_OPEN,
                            EventStatus.ACTIVE,
                        ]
                    )
                )
                .order_by(Event.event_date, Event.event_time, Event.id)
            )
        ).all()
    )
    return [
        MetricDrilldownRow(
            id=event.id,
            entity_type="event",
            entity_id=event.id,
            title=event.title,
            subtitle=f"{event.event_date.isoformat()} · {event.event_time.strftime('%H:%M')} · {event.location}",
            status=_value(event.status),
        )
        for event in events
    ]


async def _event_registrations(session: AsyncSession) -> list[MetricDrilldownRow]:
    rows = (
        await session.execute(
            select(EventRegistration, Event, User)
            .join(Event, Event.id == EventRegistration.event_id)
            .join(User, User.id == EventRegistration.user_id)
            .where(
                EventRegistration.status.in_(
                    [
                        RegistrationStatus.REGISTERED,
                        RegistrationStatus.WILL_COME,
                        RegistrationStatus.ATTENDED,
                    ]
                )
            )
            .order_by(Event.event_date, Event.id, User.first_name, User.id)
        )
    ).all()
    return [
        MetricDrilldownRow(
            id=registration.id,
            entity_type="event_registration",
            entity_id=registration.id,
            title=_full_name(user),
            subtitle=f"{event.title} · {event.event_date.isoformat()}",
            status=_value(registration.status),
        )
        for registration, event, user in rows
    ]


async def _task_results(session: AsyncSession) -> list[MetricDrilldownRow]:
    rows = (
        await session.execute(
            select(TaskSubmission, Task, User)
            .join(Task, Task.id == TaskSubmission.task_id)
            .join(User, User.id == TaskSubmission.user_id)
            .where(TaskSubmission.status == "pending")
            .order_by(TaskSubmission.created_at.desc(), TaskSubmission.id.desc())
        )
    ).all()
    return [
        MetricDrilldownRow(
            id=submission.id,
            entity_type="task_submission",
            entity_id=submission.id,
            title=task.title,
            subtitle=_full_name(user),
            status=_value(submission.status),
        )
        for submission, task, user in rows
    ]


_BUILDERS = {
    "current_roster": _current_roster,
    "active_base": _active_base,
    "projects_active": _projects_active,
    "events_live": _events_live,
    "event_registrations": _event_registrations,
    "task_results": _task_results,
}


async def build_metric_drilldown(session: AsyncSession, metric: str) -> MetricDrilldown:
    builder = _BUILDERS.get(metric)
    if builder is None:
        raise ValueError("unknown_admin_metric")
    rows = await builder(session)
    return MetricDrilldown(metric=metric, label=METRIC_LABELS[metric], rows=rows)
