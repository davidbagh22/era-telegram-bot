from __future__ import annotations

from aiogram import F, Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventRegistration, User
from app.handlers.admin.events_block6 import guard
from app.services.event_registration_service import (
    ACTIVE_REGISTRATION_STATUSES,
    event_points_already_awarded,
    registration_stats,
)
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.utils.constants import REGISTRATION_STATUS_LABELS, RegistrationStatus

router = Router(name="admin_event_registration_block14")


def _participants_keyboard(event_id: int, rows: list[tuple[EventRegistration, User]]) -> InlineKeyboardMarkup:
    buttons = []
    for registration, participant in rows:
        name = f"{participant.first_name} {participant.last_name or ''}".strip()
        buttons.append([
            InlineKeyboardButton(
                text=f"👤 {name[:28]}", callback_data=f"admin:user:{participant.id}"
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                text="✅ Был",
                callback_data=f"admin:event:attendance:attended:{event_id}:{registration.id}",
            ),
            InlineKeyboardButton(
                text="❌ Не пришёл",
                callback_data=f"admin:event:attendance:no_show:{event_id}:{registration.id}",
            ),
        ])
    buttons.append([
        InlineKeyboardButton(
            text="⭐ Начислить баллы посетившим",
            callback_data=f"admin:event:award:{event_id}",
        )
    ])
    buttons.append([InlineKeyboardButton(text="← К мероприятию", callback_data="admin:events")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("admin:event:participants:"))
async def event_participants(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        await call.message.answer("Мероприятие не найдено")
        return
    result = await session.execute(
        select(EventRegistration, User)
        .join(User, User.id == EventRegistration.user_id)
        .where(EventRegistration.event_id == event.id)
        .order_by(EventRegistration.created_at, User.first_name)
    )
    rows = list(result.all())
    stats = await registration_stats(session, event)
    if not rows:
        await call.message.answer(
            f"👥 Участники мероприятия\n\n{event.title}\n\nПока никто не зарегистрирован."
        )
        return
    lines = []
    for index, (registration, participant) in enumerate(rows, 1):
        name = f"{participant.first_name} {participant.last_name or ''}".strip()
        status = REGISTRATION_STATUS_LABELS.get(registration.status, registration.status)
        lines.append(f"{index}. {name} — {status}")
    await call.message.answer(
        f"👥 Участники мероприятия\n\n{event.title}\n"
        f"Зарегистрировано: {stats['registered']}\n"
        f"Свободных мест: {stats['free']}\n\n"
        + "\n".join(lines),
        reply_markup=_participants_keyboard(event.id, rows),
    )


@router.callback_query(F.data.regexp(r"^admin:event:attendance:(attended|no_show):\d+:\d+$"))
async def set_attendance(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await guard(call, user, settings):
        return
    _, _, _, action, raw_event_id, raw_registration_id = call.data.split(":")
    registration = await session.get(EventRegistration, int(raw_registration_id))
    if not registration or registration.event_id != int(raw_event_id):
        await call.message.answer("Регистрация не найдена")
        return
    registration.status = (
        RegistrationStatus.ATTENDED if action == "attended" else RegistrationStatus.NO_SHOW
    )
    await session.flush()
    await call.message.answer(
        "Посещение отмечено." if action == "attended" else "Отмечено, что участник не пришёл."
    )


@router.callback_query(F.data.startswith("admin:event:award:"))
async def award_event_points(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        await call.message.answer("Мероприятие не найдено")
        return
    result = await session.execute(
        select(EventRegistration, User)
        .join(User, User.id == EventRegistration.user_id)
        .where(
            EventRegistration.event_id == event.id,
            EventRegistration.status == RegistrationStatus.ATTENDED,
        )
    )
    rows = list(result.all())
    if not rows:
        await call.message.answer("Сначала отметьте участников, которые были на мероприятии.")
        return
    awarded = 0
    skipped = 0
    for registration, participant in rows:
        if await event_points_already_awarded(
            session, event_id=event.id, user_id=participant.id
        ):
            skipped += 1
            continue
        await add_points(
            session,
            user_id=participant.id,
            points=event.points_for_visit,
            reason=f"Посещение мероприятия: {event.title}",
            approved_by=user.id if user else None,
            related_event_id=event.id,
        )
        awarded += 1
        await safe_send(
            bot,
            participant.telegram_id,
            f"Участие в мероприятии «{event.title}» подтверждено.\n"
            f"Начислено: +{event.points_for_visit} баллов.",
        )
    await session.flush()
    await call.message.answer(
        f"Готово. Баллы начислены: {awarded}. Уже были начислены ранее: {skipped}."
    )
