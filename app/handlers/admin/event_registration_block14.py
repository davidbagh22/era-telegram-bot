from __future__ import annotations

from aiogram import F, Bot, Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventRegistration, User
from app.handlers.admin.events_block6 import guard
from app.services.event_registration_service import (
    event_points_already_awarded,
    registration_stats,
)
from app.services.event_participants_export import build_participants_xlsx, format_registered_at
from app.services.notification_service import safe_answer_document, safe_send
from app.services.points_service import add_points
from app.utils.constants import REGISTRATION_STATUS_LABELS, RegistrationStatus

router = Router(name="admin_event_registration_block14")

PARTICIPANTS_SHOWN = 30
_REGISTRATION_GROUPS = (
    ("✅ Зарегистрированы", {RegistrationStatus.REGISTERED, RegistrationStatus.WILL_COME}),
    ("⏳ Лист ожидания", {RegistrationStatus.WAITLIST}),
    ("🎟 Посетили", {RegistrationStatus.ATTENDED}),
    ("▫️ Остальные", None),
)


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
        InlineKeyboardButton(text="📥 Скачать Excel", callback_data=f"admin:event:xlsx:{event_id}")
    ])
    buttons.append([
        InlineKeyboardButton(
            text="✨ Управление активностями",
            callback_data=f"admin:event:activities:create:{event_id}",
        )
    ])
    if rows:
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
        .order_by(EventRegistration.created_at.desc(), EventRegistration.id.desc())
    )
    rows = list(result.all())
    stats = await registration_stats(session, event)
    if not rows:
        await call.message.answer(
            f"👥 Участники · 0\n\n{event.title}\n\nПока никто не зарегистрирован.",
            reply_markup=_participants_keyboard(event.id, rows),
        )
        return
    shown = rows[:PARTICIPANTS_SHOWN]
    placed: set[int] = set()
    sections = []
    for title, statuses in _REGISTRATION_GROUPS:
        group = [
            (registration, participant) for registration, participant in shown
            if registration.id not in placed and (statuses is None or registration.status in statuses)
        ]
        if not group:
            continue
        placed.update(registration.id for registration, _ in group)
        lines = []
        for registration, participant in group:
            name = f"{participant.first_name} {participant.last_name or ''}".strip()
            status = REGISTRATION_STATUS_LABELS.get(registration.status, registration.status)
            moment = format_registered_at(registration.created_at, settings.timezone)
            lines.append(f"• {name} — {status} · {moment}")
        sections.append(f"{title}\n" + "\n".join(lines))
    hidden = len(rows) - len(shown)
    tail = f"\n\nПоказаны {len(shown)} новых регистраций, ещё {hidden} — в Excel и в Mini App." if hidden else ""
    await call.message.answer(
        f"👥 Участники · {stats['registered']}\n\n{event.title}\n"
        f"Свободных мест: {stats['free']}\n"
        "Сначала новые регистрации.\n\n"
        + "\n\n".join(sections) + tail,
        reply_markup=_participants_keyboard(event.id, shown),
    )


@router.callback_query(F.data.regexp(r"^admin:event:xlsx:[0-9]+$"))
async def event_participants_xlsx(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await guard(call, user, settings):
        return
    event_id = int(call.data.rsplit(":", 1)[-1])
    event = await session.get(Event, event_id)
    if not event:
        await call.message.answer("Мероприятие не найдено")
        return
    rows = (await session.execute(
        select(EventRegistration, User)
        .join(User, User.id == EventRegistration.user_id)
        .where(EventRegistration.event_id == event_id)
        .order_by(EventRegistration.created_at, EventRegistration.id)
    )).all()
    await safe_answer_document(
        call.message,
        BufferedInputFile(build_participants_xlsx(rows, settings.timezone), filename=f"ERA_event_{event_id}_participants.xlsx"),
        caption=f"📋 {event.title[:200]}\nУчастников в списке: {len(rows)}",
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
            source_type="event_attendance",
            source_id=registration.id,
            idempotency_key=f"event_attendance:{event.id}:{participant.id}",
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
