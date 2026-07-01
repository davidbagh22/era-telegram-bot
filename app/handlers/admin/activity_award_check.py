from aiogram import F, Bot, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import EventActivity, EventActivitySubmission, PointTransaction, User
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.utils import texts
from app.utils.constants import Role

router = Router(name="admin_activity_award_check")


def ok(u: User | None, s: Settings, tg: int) -> bool:
    return bool(tg in s.admin_ids or (u and u.role == Role.ADMIN and not u.is_blocked))


@router.callback_query(F.data.regexp(r"^admin:activity:(approve|reject):\d+$"))
async def decide(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    await call.answer()
    if not ok(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return
    _, _, action, raw_id = call.data.split(":")
    sub = await session.get(EventActivitySubmission, int(raw_id))
    if not sub or sub.status != "pending":
        await call.message.answer("Ответ уже проверен")
        return
    activity = await session.get(EventActivity, sub.activity_id)
    target = await session.get(User, sub.user_id)
    if not activity:
        await call.message.answer("Активность не найдена")
        return
    if action == "reject":
        sub.status = "rejected"
        sub.reviewed_by = user.id if user else None
        await call.message.answer("Ответ отклонён")
        if target:
            await safe_send(bot, target.telegram_id, f"Результат «{activity.title}» пока не подтверждён")
        return
    old = await session.scalar(select(PointTransaction).where(PointTransaction.user_id == sub.user_id, PointTransaction.related_event_id == activity.event_id, PointTransaction.reason.ilike(f"%{activity.title}%"), PointTransaction.points > 0))
    sub.status = "approved"
    sub.reviewed_by = user.id if user else None
    if old:
        await call.message.answer("Ответ принят, но баллы за эту активность уже начислялись ранее")
        return
    sub.points_awarded = activity.points
    await add_points(session, user_id=sub.user_id, points=activity.points, reason=f"Активность после мероприятия: {activity.title}", approved_by=user.id if user else None, related_event_id=activity.event_id)
    await call.message.answer("Ответ принят, баллы начислены")
    if target:
        await safe_send(bot, target.telegram_id, f"Ваш результат «{activity.title}» принят — начислено {activity.points} баллов")
