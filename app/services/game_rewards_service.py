"""Game awards use the shared ledger and serialize all caps per registered user."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.database.models import PointTransaction, User
from app.services.points_service import add_points, make_idempotency_key
from app.utils.constants import ApplicationStatus


async def award_game_points(session, *, telegram_id, round_id, amount, now=None):
    if amount <= 0:
        return 0
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id).with_for_update())
    if not user or user.is_blocked or user.is_archived or user.application_status != ApplicationStatus.APPROVED:
        return 0
    key = make_idempotency_key('game', round_id, user.id, 'quiz')
    existing = await session.scalar(select(PointTransaction).where(PointTransaction.idempotency_key == key))
    if existing:
        return 0
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo('Asia/Yerevan'))
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    week = day - timedelta(days=day.weekday())
    month = day.replace(day=1)
    for start, cap in ((day, 20), (week, 100), (month, 300)):
        used = await session.scalar(select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
            PointTransaction.user_id == user.id,
            PointTransaction.source_type == 'game',
            PointTransaction.points > 0,
            PointTransaction.created_at >= start.astimezone(timezone.utc),
        ))
        amount = min(amount, max(0, cap - int(used)))
    if not amount:
        return 0
    transaction = await add_points(session, user_id=user.id, points=amount,
                     reason='Интерактив ЭРА: верный ответ', approved_by=None,
                     source_type='game', idempotency_key=key)
    transaction.created_at = now
    await session.flush()
    return amount
