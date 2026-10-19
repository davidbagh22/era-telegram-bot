"""Shared, bounded-period management metrics; no ORM collection truncation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import String, case, cast, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AuditLog, Event, EventRegistration, PointTransaction, Project,
    ProjectMember, Task, TaskSubmission, User,
)
from app.database.participation_models import ParticipationLifecycle
from app.services.meaningful_activity_service import meaningful_points_condition


@dataclass(frozen=True)
class AnalyticsMetric:
    key: str
    label: str
    value: int | float | None
    previous: int | float | None
    note: str

    @property
    def delta(self):
        return None if self.value is None or self.previous is None else round(self.value - self.previous, 1)


@dataclass(frozen=True)
class AnalyticsSnapshot:
    days: int
    as_of: datetime
    metrics: tuple[AnalyticsMetric, ...]


def roster_conditions():
    return (
        User.application_status == 'approved', User.is_archived.is_(False),
        User.is_blocked.is_(False),
        ~select(ParticipationLifecycle.user_id).where(
            ParticipationLifecycle.user_id == User.id,
            ParticipationLifecycle.participation_mode == 'EXITED',
        ).exists(),
    )


def verified_activity_facts():
    """Include zero-point confirmed results; dates are actual confirmations.

    UNION duplicates do not inflate distinct active users. Ledger rows keep
    legacy verified activity available when no structured confirmation exists.
    """
    return union_all(
        select(PointTransaction.user_id.label('user_id'), PointTransaction.created_at.label('at'), case(
            (PointTransaction.related_task_id.is_not(None), literal('task:') + cast(PointTransaction.related_task_id, String)),
            (PointTransaction.related_event_id.is_not(None), literal('event:') + cast(PointTransaction.related_event_id, String)),
            (PointTransaction.related_project_id.is_not(None), literal('project:') + cast(PointTransaction.related_project_id, String)),
            else_=None,
        ).label('result_key'))
        .where(meaningful_points_condition()),
        select(EventRegistration.user_id, EventRegistration.last_confirmation_at, literal("event:") + cast(EventRegistration.event_id, String))
        .where(EventRegistration.status == 'attended', EventRegistration.last_confirmation_at.is_not(None)),
        select(ProjectMember.user_id, ProjectMember.contribution_confirmed_at, literal("project:") + cast(ProjectMember.project_id, String))
        .where(ProjectMember.contribution_status == 'confirmed', ProjectMember.contribution_confirmed_at.is_not(None)),
        select(TaskSubmission.user_id, AuditLog.created_at, literal("task:") + cast(TaskSubmission.task_id, String))
        .join(AuditLog, (AuditLog.entity_type == 'task_submission') & (AuditLog.entity_id == TaskSubmission.id))
        .where(AuditLog.action == 'task.submission_approve', TaskSubmission.status == 'approved'),
    ).subquery()


def verified_users_between(start: datetime, end: datetime):
    facts = verified_activity_facts()
    return select(facts.c.user_id).where(
        facts.c.at >= start.astimezone(timezone.utc), facts.c.at < end.astimezone(timezone.utc),
        facts.c.user_id.in_(select(User.id).where(*roster_conditions())),
    ).distinct()


async def count_verified_users(session: AsyncSession, start: datetime, end: datetime) -> int:
    return int(await session.scalar(select(func.count()).select_from(verified_users_between(start, end).subquery())) or 0)


async def count_new_members(session: AsyncSession, start: datetime, end: datetime) -> int:
    first = select(AuditLog.entity_id.label('user_id'), func.min(AuditLog.created_at).label('at')).where(
        AuditLog.action == 'user.approved', AuditLog.entity_type == 'user',
    ).group_by(AuditLog.entity_id).subquery()
    return int(await session.scalar(select(func.count()).select_from(first).where(
        first.c.at >= start.astimezone(timezone.utc), first.c.at < end.astimezone(timezone.utc),
        first.c.user_id.in_(select(User.id).where(*roster_conditions())),
    )) or 0)


async def build_analytics_snapshot(
    session: AsyncSession, *, days: int = 30, now: datetime | None = None,
    timezone_name: str = 'Asia/Yerevan',
) -> AnalyticsSnapshot:
    if days not in (7, 30, 90):
        raise ValueError('Supported periods: 7, 30, 90 days')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must have a timezone')
    zone = ZoneInfo(timezone_name)
    end = now.astimezone(zone)
    start, older = end - timedelta(days=days), end - timedelta(days=2 * days)
    facts = verified_activity_facts()
    roster = select(User.id).where(*roster_conditions())

    async def count(statement):
        return int(await session.scalar(statement) or 0)

    def active(a, b):
        return select(facts.c.user_id).where(facts.c.at >= a.astimezone(timezone.utc), facts.c.at < b.astimezone(timezone.utc), facts.c.user_id.in_(roster)).distinct()

    async def active_count(a, b):
        return await count(select(func.count()).select_from(active(a, b).subquery()))

    current_active, previous_active = await active_count(start, end), await active_count(older, start)
    retained = await count(select(func.count()).select_from(active(start, end).where(facts.c.user_id.in_(active(older, start))).subquery()))
    prior_cohort = await active_count(older - timedelta(days=days), older)
    prior_retained = await count(select(func.count()).select_from(active(older, start).where(facts.c.user_id.in_(active(older - timedelta(days=days), older))).subquery()))
    async def approvals(a, b):
        return await count_new_members(session, a, b)

    async def events(a, b):
        # Event dates are organization-local dates. Exclude the current partial
        # day so both comparison periods contain the same number of whole days.
        return await count(select(func.count()).select_from(Event).where(Event.status.in_(['completed', 'report_submitted']), Event.event_date >= a.date(), Event.event_date < b.date()))

    pending_result = select(TaskSubmission.id).where(TaskSubmission.task_id == Task.id, TaskSubmission.status == 'pending').exists()
    attention = or_(Task.status.in_(['review', 'overdue']),
                    (Task.deadline < now) & Task.status.in_(['new', 'published', 'in_progress']),
                    pending_result & (Task.status != 'cancelled'))
    metrics = (
        AnalyticsMetric('members', 'Действующие участники', await count(select(func.count()).select_from(User).where(*roster_conditions())), None, 'Текущий состав; исторический снимок состава отсутствует'),
        AnalyticsMetric('new_members', f'Новые участники · {days} дн.', await approvals(start, end), await approvals(older, start), 'Первое одобрение по аудиту; старые записи без истории не восстанавливаются из роли'),
        AnalyticsMetric('active', f'Подтверждённо активные · {days} дн.', current_active, previous_active, 'Подтверждённый результат; должность и цифровые действия не учитываются'),
        AnalyticsMetric('retention', 'Удержание, %', round(100 * retained / previous_active, 1) if previous_active else None, round(100 * prior_retained / prior_cohort, 1) if prior_cohort else None, 'Вернувшиеся из активной когорты предыдущего периода; состав ограничен текущей базой'),
        AnalyticsMetric('funnel', 'Участник → активный → лидер', None, None, 'Наблюдаемая когорта — раздел «Рост за 90 дней»; текущая роль не доказывает переход'),
        AnalyticsMetric('events', f'Проведённые мероприятия · {days} дн.', await events(start, end), await events(older, start), 'Завершённые мероприятия за полные локальные дни; регистрация не равна явке'),
        AnalyticsMetric('projects', 'Действующие проекты', await count(select(func.count()).select_from(Project).where(Project.status == 'in_progress')), None, 'Текущий статус; история изменения состава проектов отсутствует'),
        AnalyticsMetric('attention', 'Задачи требуют внимания', await count(select(func.count()).select_from(Task).where(attention)), None, 'Просрочки и проверка; каждая задача учитывается один раз'),
    )
    return AnalyticsSnapshot(days, now, metrics)
