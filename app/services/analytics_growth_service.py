"""Observed 90-day registration cohort; roles never substitute for history."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog, User
from app.services.analytics_snapshot_service import verified_activity_facts


@dataclass(frozen=True)
class GrowthStage:
    key: str
    label: str
    count: int
    conversion: float | None
    median_days: float | None
    lost_user_ids: tuple[int, ...]


@dataclass(frozen=True)
class GrowthSnapshot:
    start: datetime
    end: datetime
    stages: tuple[GrowthStage, ...]
    approval_history_missing: int
    note: str


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def build_growth_snapshot(session: AsyncSession, *, now: datetime | None = None) -> GrowthSnapshot:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must have a timezone')
    now = now.astimezone(timezone.utc)
    start = now - timedelta(days=90)
    cohort = select(User.id.label('user_id'), User.created_at.label('at')).where(
        User.created_at >= start, User.created_at < now,
    ).cte('growth_cohort')
    approval = select(cohort.c.user_id, func.min(AuditLog.created_at).label('at')).join(
        AuditLog, AuditLog.entity_id == cohort.c.user_id,
    ).where(AuditLog.action == 'user.approved', AuditLog.entity_type == 'user',
            AuditLog.created_at >= cohort.c.at, AuditLog.created_at < now).group_by(cohort.c.user_id).cte('growth_approval')
    facts = verified_activity_facts()
    # Several point awards and the attendance confirmation for one event are
    # one participation. Unknown legacy entity IDs cannot prove a repeat.
    results = select(facts.c.user_id, facts.c.result_key, func.min(facts.c.at).label('at')).join(
        approval, approval.c.user_id == facts.c.user_id,
    ).where(facts.c.result_key.is_not(None), facts.c.at >= approval.c.at, facts.c.at < now
            ).group_by(facts.c.user_id, facts.c.result_key).cte('growth_results')
    ordered = select(results.c.user_id, results.c.at, func.row_number().over(
        partition_by=results.c.user_id, order_by=(results.c.at, results.c.result_key),
    ).label('rank')).cte('growth_ordered')
    first = select(ordered.c.user_id, ordered.c.at).where(ordered.c.rank == 1).cte('growth_first')
    repeat = select(ordered.c.user_id, ordered.c.at).where(ordered.c.rank == 2).cte('growth_repeat')

    def transition(previous, role, name):
        return select(previous.c.user_id, func.min(AuditLog.created_at).label('at')).join(
            AuditLog, AuditLog.entity_id == previous.c.user_id,
        ).where(AuditLog.entity_type == 'user', AuditLog.action == 'user.role_changed',
                AuditLog.new_value['role'].as_string() == role,
                AuditLog.created_at >= previous.c.at, AuditLog.created_at < now,
                ).group_by(previous.c.user_id).cte(name)

    active = transition(repeat, 'activist', 'growth_active')
    leader = transition(active, 'leader', 'growth_leader')
    tables = [cohort, approval, first, repeat, active, leader]
    statement = select(cohort.c.user_id, *(table.c.at for table in tables)).select_from(cohort)
    for table in tables[1:]:
        statement = statement.outerjoin(table, table.c.user_id == cohort.c.user_id)
    rows = (await session.execute(statement)).all()
    labels = [('registered', 'Регистрация'), ('approved', 'Одобрение'), ('first', 'Первый результат'),
              ('repeat', 'Повторное участие'), ('active', 'Переход в активисты'), ('leader', 'Переход в лидеры')]
    stages = []
    for index, (key, label) in enumerate(labels):
        reached = [row for row in rows if row[index + 1] is not None]
        previous = [row for row in rows if row[index] is not None] if index else rows
        durations = [(_aware(row[index + 1]) - _aware(row[index])).total_seconds() / 86400
                     for row in reached] if index else []
        lost = tuple(row[0] for row in previous if row[index + 1] is None) if index else ()
        stages.append(GrowthStage(key, label, len(reached),
                                  round(len(reached) * 100 / len(previous), 1) if previous else None,
                                  round(median(durations), 1) if durations else None, lost))
    missing = int(await session.scalar(select(func.count()).select_from(cohort).join(User, User.id == cohort.c.user_id).where(
        User.application_status == 'approved', ~cohort.c.user_id.in_(select(approval.c.user_id)),
    )) or 0)
    return GrowthSnapshot(start, now, tuple(stages), missing,
        'Наблюдаемая последовательность за 90 дней, включая незавершённые анкеты. '
        'Одобрение и роли только по аудиту; первый и второй разные event/task/project после одобрения. '
        'Отсутствующая история и ещё не совершённое действие неразличимы: разрыв не доказывает уход. '
        'Раннее назначение до предыдущего этапа не считается последовательным переходом. '
        'Срок — медиана дней между наблюдаемыми этапами; окна новых участников ещё не завершены.')
