from datetime import datetime, timedelta, timezone
from sqlalchemy import Date, cast, func, select
from app.database.models import AuditLog, User
from app.services.analytics_snapshot_service import count_new_members, count_verified_users, roster_conditions
from app.services.telegram_analytics_service import telegram_snapshot


def metric(key, label, value, *, period, source, explanation, previous=None, denominator=None):
    return dict(id=key, label=label, value=value, unit='человек', period=period,
        previous_value=previous, delta=(value - previous if value is not None and previous is not None else None),
        numerator=value, denominator=denominator, data_state='valid' if value is not None else 'unavailable',
        source=source, explanation=explanation, updated_at=datetime.now(timezone.utc).isoformat(), drilldown=None)


async def build_v2_snapshot(session, settings, *, start, end, now=None):
    now = now or datetime.now(timezone.utc)
    effective_end = min(end, now)
    previous_end = effective_end - (end - start)
    roster = int(await session.scalar(select(func.count(User.id)).where(*roster_conditions())) or 0)
    records = int(await session.scalar(select(func.count(User.id)).where(User.is_archived.is_(False))) or 0)
    new = await count_new_members(session, start, effective_end)
    active = await count_verified_users(session, start, effective_end)
    previous_start = start - (end - start)
    previous_new = await count_new_members(session, previous_start, previous_end)
    previous_active = await count_verified_users(session, previous_start, previous_end)
    label = f'{start:%d.%m.%Y}–{(end.date()).strftime("%d.%m.%Y")} (конец не включён)'
    snapshot = await telegram_snapshot(session, settings, start=start, end=end, now=now)
    snapshot['metrics'] = [
        metric('roster', 'Текущий состав', roster, period='На дату формирования', source='User + ParticipationLifecycle',
               explanation='Одобрены, не заблокированы, не архивированы и не вышли из ЭРА.'),
        metric('records', 'Профилей в базе', records, period='На дату формирования', source='User',
               explanation='Все неархивные профили, включая заявки и неодобренные аккаунты. Это не текущий состав.'),
        metric('new_members', 'Новые участники', new, period=label, source='AuditLog: первое одобрение', previous=previous_new,
               explanation='Первые одобрения за выбранные даты среди текущего состава. Старые записи без аудита не восстановлены.'),
        metric('verified_active', 'С подтверждённым результатом', active, period=label, source='Verified activity facts',
               denominator=roster, previous=previous_active,
               explanation='Текущий состав с подтверждённым посещением или результатом задачи/проекта. Переписка и просмотры сюда не входят.')]
    first = select(AuditLog.entity_id.label('user_id'), func.min(AuditLog.created_at).label('at')).where(
        AuditLog.action == 'user.approved', AuditLog.entity_type == 'user').group_by(AuditLog.entity_id).subquery()
    day_expr = (cast(func.timezone(settings.timezone, first.c.at), Date) if session.bind.dialect.name == 'postgresql'
                else func.date(first.c.at, f'{int(start.utcoffset().total_seconds() // 60):+d} minutes'))
    counts = {str(day): count for day, count in (await session.execute(select(day_expr, func.count()).where(
        first.c.at >= start.astimezone(timezone.utc), first.c.at < effective_end.astimezone(timezone.utc),
        first.c.user_id.in_(select(User.id).where(*roster_conditions()))).group_by(day_expr))).all()}
    snapshot['member_growth'] = [{'date': (start.date()+timedelta(days=i)).isoformat(),
        'value': counts.get((start.date()+timedelta(days=i)).isoformat(), 0),
        'observed': counts.get((start.date()+timedelta(days=i)).isoformat(), 0)} for i in range((end-start).days)]
    return snapshot
