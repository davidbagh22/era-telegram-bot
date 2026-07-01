from aiogram import F, Bot, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AttendanceProof, Event, EventRegistration, PointTransaction, User
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.services.portfolio_service import add_portfolio_item
from app.utils import texts
from app.utils.constants import RegistrationStatus, Role

router = Router(name="admin_event_points_check")


def is_admin(u: User | None, s: Settings, tg_id: int) -> bool:
    return bool(tg_id in s.admin_ids or (u and u.role == Role.ADMIN and not u.is_blocked))


async def has_visit_points(session: AsyncSession, user_id: int, event_id: int) -> bool:
    row = await session.scalar(
        select(PointTransaction).where(
            PointTransaction.user_id == user_id,
            PointTransaction.related_event_id == event_id,
            PointTransaction.points > 0,
        )
    )
    return row is not None


@router.callback_query(F.data.regexp(r"^admin:event:attend:\d+:\d+$"))
async def attend_once(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    await call.answer()
    if not is_admin(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return
    _, _, _, raw_event_id, raw_user_id = call.data.split(":")
    event_id, target_id = int(raw_event_id), int(raw_user_id)
    event = await session.get(Event, event_id)
    target = await session.get(User, target_id)
    registration = await session.scalar(
        select(EventRegistration).where(EventRegistration.event_id == event_id, EventRegistration.user_id == target_id)
    )
    if not event or not registration:
        await call.message.answer("Event registration not found")
        return
    registration.status = RegistrationStatus.ATTENDED
    if await has_visit_points(session, target_id, event_id):
        await call.message.answer("Attendance confirmed. Points for this event were already added earlier.")
        return
    await add_points(session, user_id=target_id, points=event.points_for_visit, reason=f"Event attendance: {event.title}", approved_by=user.id if user else None, related_event_id=event.id)
    await add_portfolio_item(session, user_id=target_id, title=f"Участие: {event.title}", item_type="event", description="Участие подтверждено командой ЭРА", issued_by=user.id if user else None, related_event_id=event.id)
    await call.message.answer("Attendance confirmed. Points added once.")
    if target:
        await safe_send(bot, target.telegram_id, f"Ваше участие в «{event.title}» подтверждено — начислено {event.points_for_visit} баллов")


@router.callback_query(F.data.startswith("admin:proof:approve:"))
async def selfie_once(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    await call.answer()
    if not is_admin(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return
    proof = await session.get(AttendanceProof, int(call.data.rsplit(":", 1)[-1]))
    if not proof or proof.status != "pending":
        await call.message.answer("Selfie already reviewed")
        return
    event = await session.get(Event, proof.event_id)
    target = await session.get(User, proof.user_id)
    proof.status = "approved"
    proof.reviewed_by = user.id if user else None
    reg = await session.scalar(select(EventRegistration).where(EventRegistration.event_id == proof.event_id, EventRegistration.user_id == proof.user_id))
    if reg:
        reg.status = RegistrationStatus.ATTENDED
    already = await has_visit_points(session, proof.user_id, proof.event_id)
    points = 5 if already else ((event.points_for_visit if event else 5) + 5)
    await add_points(session, user_id=proof.user_id, points=points, reason="Selfie attendance proof", approved_by=user.id if user else None, related_event_id=proof.event_id)
    if not already:
        await add_portfolio_item(session, user_id=proof.user_id, title=f"Участие: {event.title if event else 'мероприятие ЭРА'}", item_type="event", description="Участие подтверждено командой ЭРА", issued_by=user.id if user else None, related_event_id=proof.event_id)
    await call.message.answer(f"Selfie approved. Points added: {points}")
    if target:
        await safe_send(bot, target.telegram_id, f"Ваше участие подтверждено — начислено {points} баллов")
