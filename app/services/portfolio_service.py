from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Badge,
    Event,
    EventActivitySubmission,
    EventRegistration,
    Office,
    PortfolioItem,
    Project,
    Task,
    TaskSubmission,
    User,
    UserBadge,
    UserOffice,
)
from app.repositories.users import user_stats
from app.utils.constants import (
    EVENT_STATUS_LABELS,
    PROJECT_STATUS_LABELS,
    REGISTRATION_STATUS_LABELS,
    ROLE_LABELS,
    STATUS_LABELS,
    TASK_STATUS_LABELS,
)


@dataclass(frozen=True)
class PortfolioEntry:
    title: str
    description: str = ""
    status: str = ""
    date_label: str = ""
    category: str = ""
    file_id: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class PortfolioData:
    full_name: str
    role: str
    participation_status: str
    departments: list[str]
    directions: list[str]
    period: str
    city: str = ""
    email: str = ""
    education_work: str = ""
    occupation: str = ""
    experience: str = ""
    motivation: str = ""
    skills: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    projects: list[PortfolioEntry] = field(default_factory=list)
    events: list[PortfolioEntry] = field(default_factory=list)
    tasks: list[PortfolioEntry] = field(default_factory=list)
    volunteer: list[PortfolioEntry] = field(default_factory=list)
    leadership: list[PortfolioEntry] = field(default_factory=list)
    badges: list[PortfolioEntry] = field(default_factory=list)
    certificates: list[PortfolioEntry] = field(default_factory=list)
    recommendations: list[PortfolioEntry] = field(default_factory=list)
    uploaded_items: list[PortfolioEntry] = field(default_factory=list)
    confirmed_items: list[PortfolioEntry] = field(default_factory=list)
    pending_items: list[PortfolioEntry] = field(default_factory=list)


def _clean(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "none" else text


def _name(user: User) -> str:
    return " ".join(part for part in (_clean(user.first_name), _clean(user.last_name)) if part) or "Участник ЭРА"


def _date_label(value: date | datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%d.%m.%Y")


def _period(user: User) -> str:
    created_at = getattr(user, "created_at", None)
    if created_at is None:
        return "период участия уточняется"
    return f"с {_date_label(created_at)}"


def _limited(items: list[PortfolioEntry], limit: int = 12) -> list[PortfolioEntry]:
    return items[:limit]


def _portfolio_entry(item: PortfolioItem) -> PortfolioEntry:
    status = "подтверждено" if item.status == "verified" else "на проверке"
    return PortfolioEntry(
        title=_clean(item.title),
        description=_clean(item.description) or _clean(item.item_type),
        status=status,
        date_label=_date_label(item.issued_at or item.created_at),
        category=_clean(item.item_type),
        file_id=item.file_id,
        url=item.url,
    )


async def build_portfolio_data(session: AsyncSession, user: User) -> PortfolioData:
    stats = await user_stats(session, user.id)
    portfolio_items = list(
        (
            await session.scalars(
                select(PortfolioItem)
                .where(
                    PortfolioItem.user_id == user.id,
                    PortfolioItem.status.in_(["verified", "pending"]),
                )
                .order_by(desc(PortfolioItem.created_at), desc(PortfolioItem.id))
            )
        ).all()
    )
    projects = list(
        (
            await session.scalars(
                select(Project)
                .where(Project.author_id == user.id)
                .order_by(desc(Project.created_at), desc(Project.id))
            )
        ).all()
    )
    event_rows = list(
        (
            await session.execute(
                select(EventRegistration, Event)
                .join(Event, Event.id == EventRegistration.event_id)
                .where(EventRegistration.user_id == user.id)
                .order_by(desc(Event.event_date), desc(Event.id))
            )
        ).all()
    )
    task_rows = list(
        (
            await session.execute(
                select(TaskSubmission, Task)
                .join(Task, Task.id == TaskSubmission.task_id)
                .where(TaskSubmission.user_id == user.id)
                .order_by(desc(TaskSubmission.created_at), desc(TaskSubmission.id))
            )
        ).all()
    )
    activity_rows = list(
        (
            await session.scalars(
                select(EventActivitySubmission)
                .where(EventActivitySubmission.user_id == user.id)
                .order_by(desc(EventActivitySubmission.created_at), desc(EventActivitySubmission.id))
            )
        ).all()
    )
    badge_rows = list(
        (
            await session.execute(
                select(UserBadge, Badge)
                .join(Badge, Badge.id == UserBadge.badge_id)
                .where(UserBadge.user_id == user.id)
                .order_by(desc(UserBadge.created_at), Badge.name)
            )
        ).all()
    )
    office_rows = list(
        (
            await session.execute(
                select(UserOffice, Office)
                .join(Office, Office.id == UserOffice.office_id)
                .where(UserOffice.user_id == user.id, UserOffice.is_active.is_(True))
                .order_by(desc(UserOffice.starts_at), Office.sort_order, Office.title)
            )
        ).all()
    )

    confirmed_items = [_portfolio_entry(item) for item in portfolio_items if item.status == "verified"]
    pending_items = [_portfolio_entry(item) for item in portfolio_items if item.status == "pending"]
    certificates = [item for item in confirmed_items if item.category == "certificate"]
    recommendations = [
        item
        for item in confirmed_items
        if item.category in {"recommendation", "leader_recommendation", "partner_recommendation"}
    ]

    return PortfolioData(
        full_name=_name(user),
        role=ROLE_LABELS.get(user.role, _clean(user.role)),
        participation_status=STATUS_LABELS.get(user.participation_status, _clean(user.participation_status)),
        departments=[item.department.name for item in user.departments if item.department],
        directions=[item.direction.name for item in user.directions if item.direction],
        period=_period(user),
        city=_clean(user.city),
        email=_clean(user.email),
        education_work=_clean(user.education_work),
        occupation=_clean(user.occupation),
        experience=_clean(user.experience),
        motivation=_clean(user.motivation),
        skills=[_clean(item) for item in (user.skills or []) if _clean(item)],
        stats=stats,
        projects=_limited(
            [
                PortfolioEntry(
                    title=_clean(project.title),
                    description=_clean(project.short_description),
                    status=PROJECT_STATUS_LABELS.get(project.status, _clean(project.status)),
                    date_label=_date_label(project.submitted_at or project.created_at),
                    category="project",
                )
                for project in projects
            ]
        ),
        events=_limited(
            [
                PortfolioEntry(
                    title=_clean(event.title),
                    description=_clean(event.description),
                    status=REGISTRATION_STATUS_LABELS.get(registration.status, _clean(registration.status)),
                    date_label=_date_label(event.event_date),
                    category=EVENT_STATUS_LABELS.get(event.status, _clean(event.status)),
                )
                for registration, event in event_rows
            ]
        ),
        tasks=_limited(
            [
                PortfolioEntry(
                    title=_clean(task.title),
                    description=_clean(submission.text) or _clean(task.description),
                    status=TASK_STATUS_LABELS.get(submission.status, _clean(submission.status)),
                    date_label=_date_label(submission.created_at),
                    category="task",
                    file_id=submission.file_id,
                )
                for submission, task in task_rows
            ]
        ),
        volunteer=_limited(
            [
                PortfolioEntry(
                    title="Активность после мероприятия",
                    description=_clean(submission.text) or "подтверждение активности",
                    status=TASK_STATUS_LABELS.get(submission.status, _clean(submission.status)),
                    date_label=_date_label(submission.created_at),
                    category="volunteer",
                    file_id=submission.file_id,
                )
                for submission in activity_rows
            ]
        ),
        leadership=_limited(
            [
                PortfolioEntry(
                    title=_clean(office.title),
                    description=_clean(office.description),
                    status="активная роль",
                    date_label=_date_label(user_office.starts_at),
                    category="leadership",
                )
                for user_office, office in office_rows
            ]
        ),
        badges=_limited(
            [
                PortfolioEntry(
                    title=_clean(badge.name),
                    description=_clean(badge.description) or _clean(user_badge.reason),
                    status="подтверждено",
                    date_label=_date_label(user_badge.created_at),
                    category="badge",
                )
                for user_badge, badge in badge_rows
            ]
        ),
        certificates=_limited(certificates),
        recommendations=_limited(recommendations),
        uploaded_items=_limited([_portfolio_entry(item) for item in portfolio_items]),
        confirmed_items=_limited(confirmed_items),
        pending_items=_limited(pending_items),
    )


def portfolio_summary_text(data: PortfolioData) -> str:
    departments = ", ".join(data.departments) or "пока не выбраны"
    directions = ", ".join(data.directions) or "пока не выбраны"
    skills = ", ".join(data.skills[:8]) or "пока не указаны"
    lines = [
        "🎓 Портфолио ЭРА",
        "",
        f"{data.full_name}",
        f"Роль: {data.role}",
        f"Статус роста: {data.participation_status}",
        f"Период участия: {data.period}",
        f"Департамент: {departments}",
        f"Направление: {directions}",
        "",
        "Что уже собрано:",
        f"• мероприятия: {data.stats.get('events', 0)}",
        f"• проекты: {data.stats.get('projects', 0)}",
        f"• задачи: {data.stats.get('tasks', 0)}",
        f"• баллы: {data.stats.get('points', 0)}",
        f"• подтверждённые достижения: {len(data.confirmed_items)}",
        f"• на проверке: {len(data.pending_items)}",
        f"• знаки: {len(data.badges)}",
        f"• сертификаты: {len(data.certificates)}",
        "",
        f"Компетенции: {skills}",
        "",
        "В документ попадут подтверждённые достижения, проекты, мероприятия, задачи, роли и основные данные профиля.",
    ]
    return "\n".join(lines)
