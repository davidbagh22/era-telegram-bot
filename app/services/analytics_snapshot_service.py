"""Shared, bounded-period management metrics; no ORM collection truncation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import String, and_, case, cast, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AuditLog, Event, EventRegistration, LeadershipAttentionItem, PointTransaction, Project,
    ProjectMember, Task, TaskSubmission, User,
)
from app.database.participation_models import ParticipationLifecycle
from app.services.meaningful_activity_service import meaningful_points_condition

ACTIVE_PROJECT_STATUSES = ('approved', 'in_progress')


def held_events_between(start: datetime, end: datetime):
    """Confirmed event dates over complete organization-local calendar days."""
    return select(Event.id).where(Event.status.in_(['completed', 'report_submitted']),
                                  Event.event_date >= start.date(), Event.event_date < end.date())


def task_attention_condition(now: datetime):
    pending_result = select(TaskSubmission.id).where(
        TaskSubmission.task_id == Task.id, TaskSubmission.status == 'pending').exists()
    blocker = select(LeadershipAttentionItem.id).where(
        LeadershipAttentionItem.scope_type == 'task', LeadershipAttentionItem.scope_id == Task.id,
        LeadershipAttentionItem.status.in_(['open', 'in_progress']),
    ).exists()
    return and_(Task.status.not_in(['completed', 'cancelled']), or_(
        Task.status.in_(['review', 'overdue']),
        (Task.deadline < now) & Task.status.in_(['new', 'published', 'in_progress']),
        pending_result, blocker,
    ))


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


async def activity_cohort_counts(session: AsyncSession, *, now: datetime, days: int = 30) -> tuple[int, int, int, int, int]:
    current = verified_users_between(now-timedelta(days=days), now)
    previous = verified_users_between(now-timedelta(days=2*days), now-timedelta(days=days))
    older = verified_users_between(now-timedelta(days=3*days), now-timedelta(days=2*days))
    def number(query):
        return select(func.count()).select_from(query.subquery()).scalar_subquery()
    # Ratios must use one PostgreSQL snapshot even if roster eligibility is
    # changed concurrently with this read. No mixed numerator/denominator.
    row = (await session.execute(select(number(current), number(previous), number(current.intersect(previous)),
                                        number(older), number(previous.intersect(older))))).one()
    return tuple(map(int, row))


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

    async def count(statement):
        return int(await session.scalar(statement) or 0)

    current_active, previous_active, retained, prior_cohort, prior_retained = await activity_cohort_counts(
        session, now=end, days=days)
    async def approvals(a, b):
        return await count_new_members(session, a, b)

    async def events(a, b):
        # Event dates are organization-local dates. Exclude the current partial
        # day so both comparison periods contain the same number of whole days.
        return await count(select(func.count()).select_from(held_events_between(a, b).subquery()))

    attention = task_attention_condition(now)
    metrics = (
        AnalyticsMetric('members', 'Действующие участники', await count(select(func.count()).select_from(User).where(*roster_conditions())), None, 'Текущий состав; исторический снимок состава отсутствует'),
        AnalyticsMetric('new_members', f'Новые участники · {days} дн.', await approvals(start, end), await approvals(older, start), 'Первое одобрение по аудиту; старые записи без истории не восстанавливаются из роли'),
        AnalyticsMetric('active', f'Подтверждённо активные · {days} дн.', current_active, previous_active, 'Подтверждённый результат; должность и цифровые действия не учитываются'),
        AnalyticsMetric('retention', 'Удержание, %', round(100 * retained / previous_active, 1) if previous_active else None, round(100 * prior_retained / prior_cohort, 1) if prior_cohort else None, 'Вернувшиеся из активной когорты предыдущего периода; состав ограничен текущей базой'),
        AnalyticsMetric('funnel', 'Участник → активный → лидер', None, None, 'Наблюдаемая когорта — раздел «Рост за 90 дней»; текущая роль не доказывает переход'),
        AnalyticsMetric('events', f'Проведённые мероприятия · {days} дн.', await events(start, end), await events(older, start), 'Завершённые мероприятия за полные локальные дни; регистрация не равна явке'),
        AnalyticsMetric('projects', 'Действующие проекты', await count(select(func.count()).select_from(Project).where(Project.status.in_(ACTIVE_PROJECT_STATUSES))), None, 'Одобренные и в работе; исторический состав проектов неизвестен'),
        AnalyticsMetric('attention', 'Задачи требуют внимания', await count(select(func.count()).select_from(Task).where(attention)), None, 'Просрочки, открытые блокеры и проверка; каждая незакрытая задача учитывается один раз'),
    )
    return AnalyticsSnapshot(days, now, metrics)


async def build_event_analytics(session: AsyncSession, *, days=30, now=None, timezone_name='Asia/Yerevan') -> AnalyticsSnapshot:
    from app.database.models import Feedback
    if days not in (7, 30, 90):
        raise ValueError('Supported periods: 7, 30, 90 days')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must have a timezone')
    end = now.astimezone(ZoneInfo(timezone_name))
    start, older = end - timedelta(days=days), end - timedelta(days=2*days)
    first_visit = select(EventRegistration.user_id.label('user_id'), func.min(Event.event_date).label('day')).join(
        Event, Event.id == EventRegistration.event_id,
    ).where(EventRegistration.status == 'attended').group_by(EventRegistration.user_id).subquery()

    async def period(a, b):
        held = held_events_between(a, b)
        created_query = select(func.count()).select_from(Event).where(
            Event.created_at >= a.astimezone(timezone.utc), Event.created_at < b.astimezone(timezone.utc)).scalar_subquery()
        held_query = select(func.count()).select_from(held.subquery()).scalar_subquery()
        rating_count = select(func.count(Feedback.id)).where(Feedback.event_id.in_(held)).scalar_subquery()
        average_query = select(func.avg(Feedback.rating)).where(Feedback.event_id.in_(held)).scalar_subquery()
        visitor_feedback = select(func.count(Feedback.id)).join(EventRegistration,
            (EventRegistration.event_id == Feedback.event_id) & (EventRegistration.user_id == Feedback.user_id)
        ).where(Feedback.event_id.in_(held), EventRegistration.status == 'attended').scalar_subquery()
        eligible = EventRegistration.status.in_(['registered', 'will_come', 'attended', 'no_show'])
        present = EventRegistration.status == 'attended'
        first_condition = and_(present, first_visit.c.day >= a.date(), first_visit.c.day < b.date())
        # One statement keeps numerator, denominator and visitor cohorts on the
        # same PostgreSQL snapshot while late attendance is being confirmed.
        created, count, regs, attended, visitors, first, ratings, average, visitor_ratings = (await session.execute(select(
            created_query, held_query, func.count().filter(eligible), func.count().filter(present),
            func.count(func.distinct(EventRegistration.user_id)).filter(present),
            func.count(func.distinct(EventRegistration.user_id)).filter(first_condition), rating_count, average_query, visitor_feedback,
        ).select_from(EventRegistration).outerjoin(first_visit, first_visit.c.user_id == EventRegistration.user_id)
          .where(EventRegistration.event_id.in_(held)))).one()
        return dict(created=created, held=count, registrations=regs, attended=attended,
                    attendance=round(100*attended/regs, 1) if regs else None,
                    first=first, returning=visitors-first, ratings=ratings,
                    average=round(float(average), 1) if average is not None else None,
                    feedback_coverage=round(100*visitor_ratings/attended, 1) if attended else None)

    current, previous = await period(start, end), await period(older, start)
    definitions = [
        ('created', 'Созданы', 'Создание за выбранный период, включая черновики'),
        ('held', 'Проведены', 'completed/report_submitted, полные локальные дни'),
        ('registrations', 'Регистрации с обязательством прийти', 'registered/will_come/attended/no_show; waitlist и отмены исключены'),
        ('attended', 'Подтверждённые посещения', 'Статус attended, независимо от баллов'),
        ('attendance', 'Явка, %', 'Подтверждённые посещения / регистрации с обязательством прийти'),
        ('first', 'Первое известное посещение', 'Уникальные посетители; первая подтверждённая дата в имеющемся реестре'),
        ('returning', 'Вернувшиеся посетители', 'Уникальные посетители с подтверждённым посещением до периода'),
        ('ratings', 'Оставлено отзывов', 'Только фактически оставленные отзывы по проведённым событиям'),
        ('average', 'Средняя оценка', 'Отсутствующий отзыв не становится нулевой оценкой'),
        ('feedback_coverage', 'Охват отзывами посетителей, %', 'Отзывы подтверждённых посетителей / подтверждённые посещения'),
    ]
    return AnalyticsSnapshot(days, now, tuple(AnalyticsMetric(key, label, current[key], previous[key], note)
                                             for key, label, note in definitions))


async def build_project_analytics(session: AsyncSession, *, days=30, now=None, timezone_name='Asia/Yerevan') -> AnalyticsSnapshot:
    from app.database.models import ProjectMilestone
    if days not in (7, 30, 90):
        raise ValueError('Supported periods: 7, 30, 90 days')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must have a timezone')
    end = now.astimezone(ZoneInfo(timezone_name))
    start, older = (end - timedelta(days=days)).astimezone(timezone.utc), (end - timedelta(days=2*days)).astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    status_groups = [('ideas', 'Черновики идей', ['draft']),
                     ('review', 'На рассмотрении', ['pending_review', 'initial_review', 'venue_review', 'needs_revision']),
                     ('approved', 'Одобрены', ['approved']), ('active', 'Действующие', ['in_progress']),
                     ('completed', 'Завершены', ['completed'])]
    counts = (await session.execute(select(*(func.count().filter(Project.status.in_(statuses))
                                              for _, _, statuses in status_groups)).select_from(Project))).one()
    metrics = [AnalyticsMetric(key, label, int(value), None, 'Текущий статус; исторический снимок отсутствует')
               for (key, label, _), value in zip(status_groups, counts)]

    async def count(model, *conditions):
        return int(await session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)

    for key, label, model, stamp, conditions in [
        ('created', 'Созданы за период', Project, Project.created_at, []),
        ('contributions', 'Подтверждённые вклады', ProjectMember, ProjectMember.contribution_confirmed_at, [ProjectMember.contribution_status == 'confirmed']),
        ('milestones', 'Завершённые этапы за период', ProjectMilestone, ProjectMilestone.completed_at, [ProjectMilestone.status == 'completed']),
    ]:
        metrics.append(AnalyticsMetric(key, label, await count(model, *conditions, stamp >= start, stamp < end),
                                       await count(model, *conditions, stamp >= older, stamp < start),
                                       'По фактической дате создания/подтверждения/завершения; не по updated_at'))
    people = int(await session.scalar(select(func.count(func.distinct(ProjectMember.user_id))).where(ProjectMember.status == 'accepted')) or 0)
    metrics.append(AnalyticsMetric('participants', 'Принятые участники', people, None,
                                   'Уникальные принятые участники в реестре; автор без отдельного участия не добавляется'))
    overdue = int(await session.scalar(select(func.count()).select_from(ProjectMilestone).join(Project, Project.id == ProjectMilestone.project_id)
        .where(Project.status.in_(['approved', 'in_progress']), ProjectMilestone.deadline < now,
               ProjectMilestone.status.not_in(['completed', 'cancelled']))) or 0)
    metrics.append(AnalyticsMetric('overdue', 'Просроченные этапы', overdue, None,
                                   'Незакрытые этапы одобренных/действующих проектов с прошедшим сроком'))
    contribution = select(ProjectMember.id).where(ProjectMember.project_id == Project.id,
        ProjectMember.contribution_status == 'confirmed', ProjectMember.contribution_confirmed_at >= start,
        ProjectMember.contribution_confirmed_at < end).exists()
    milestone = select(ProjectMilestone.id).where(ProjectMilestone.project_id == Project.id,
        ProjectMilestone.status == 'completed', ProjectMilestone.completed_at >= start, ProjectMilestone.completed_at < end).exists()
    task_result = select(TaskSubmission.id).join(Task, Task.id == TaskSubmission.task_id).join(
        AuditLog, (AuditLog.entity_type == 'task_submission') & (AuditLog.entity_id == TaskSubmission.id),
    ).where(Task.project_id == Project.id, TaskSubmission.status == 'approved', AuditLog.action == 'task.submission_approve',
            AuditLog.created_at >= start, AuditLog.created_at < end).exists()
    no_results = await count(Project, Project.status.in_(['approved', 'in_progress']), Project.created_at < start,
                             ~contribution, ~milestone, ~task_result)
    metrics.append(AnalyticsMetric('without_results', f'Без подтверждённых результатов · {days} дн.', no_results, None,
        'Проект существует весь период; нет подтверждённого вклада, завершённого этапа или принятого задания. Это повод проверить процесс, не оценка качества.'))
    return AnalyticsSnapshot(days, now, tuple(metrics))


async def delivery_problem_counts(session: AsyncSession, *, days=30, now=None) -> dict[str, int]:
    from app.database.system_models import NotificationDelivery
    now = now or datetime.now(timezone.utc)
    rows = (await session.execute(select(NotificationDelivery.notification_type, func.count()).where(
        NotificationDelivery.last_attempt_at >= now-timedelta(days=days), NotificationDelivery.last_attempt_at < now,
        NotificationDelivery.status.in_(['failed', 'blocked', 'unreachable', 'uncertain', 'conflict']),
        NotificationDelivery.notification_type.in_(['management_report', 'admin_broadcast', 'leaders_broadcast']),
    ).group_by(NotificationDelivery.notification_type))).all()
    values = dict(rows)
    return {'reports': int(values.get('management_report', 0)),
            'broadcasts': int(values.get('admin_broadcast', 0) + values.get('leaders_broadcast', 0))}
