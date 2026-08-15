from __future__ import annotations

from aiogram import F, Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, User
from app.services.event_qr_service import CHECKIN_EVENT_STATUSES, qr_png
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role
from app.utils.deep_links import attendance_deep_link

router = Router(name="participant_event_qr")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


def _admin(user: User | None) -> bool:
    return bool(
        user
        and (
            user.role == Role.ADMIN
            or any(
                grant.is_active
                for grant in (getattr(user, "permission_grants", None) or [])
            )
        )
    )


def _can_manage_qr(user: User | None) -> bool:
    return bool(user and (_admin(user) or user.role in PRIVILEGED_ROLES))


async def _available_events(session: AsyncSession, user: User) -> list[Event]:
    query = (
        select(Event)
        .where(Event.status.in_(CHECKIN_EVENT_STATUSES))
        .order_by(Event.event_date, Event.event_time)
        .limit(12)
    )
    # Admins can operationally check in any event. Leaders only see events
    # explicitly assigned to them; this prevents a role from silently gaining
    # control over another team's attendance flow.
    if not _admin(user):
        query = query.where(Event.responsible_id == user.id)
    return list((await session.scalars(query)).all())


async def _send_picker(message: Message, user: User, session: AsyncSession) -> None:
    events = await _available_events(session, user)
    if not events:
        await message.answer(
            "🎟 QR вход\n\nНет доступных мероприятий, где вы назначены ответственным. "
            "Администратор может открыть QR для любого активного события."
        )
        return
    rows = [
        [
            InlineKeyboardButton(
                text=f"{event.event_date:%d.%m} · {event.title[:38]}",
                callback_data=f"event_qr:generate:{event.id}",
            )
        ]
        for event in events
    ]
    rows.append([InlineKeyboardButton(text="← Навигация", callback_data="nav:guide")])
    await message.answer(
        "🎟 QR вход на событие\n\n"
        "Выберите мероприятие. Покажите QR на входе — зарегистрированный участник "
        "сканирует его камерой, открывает бота и получает отметку посещения автоматически.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _generate(
    message: Message,
    user: User,
    event: Event,
    bot: Bot,
    settings: Settings,
) -> None:
    if not _admin(user) and event.responsible_id != user.id:
        await message.answer("У вас нет доступа к QR этого мероприятия.")
        return
    me = await bot.get_me()
    if not me.username:
        await message.answer("Не удалось сформировать QR: у бота не настроен username.")
        return
    link = attendance_deep_link(me.username, event.id, settings.bot_token)
    image = BufferedInputFile(qr_png(link), filename=f"era-event-{event.id}-qr.png")
    await message.answer_photo(
        image,
        caption=(
            f"🎟 Вход · {event.title}\n\n"
            f"📅 {event.event_date:%d.%m.%Y} · {event.event_time:%H:%M}\n"
            f"📍 {event.location}\n\n"
            "Участник должен быть заранее зарегистрирован. Отметка работает только "
            "в окне проведения события; повторное сканирование не начисляет баллы второй раз."
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Другой QR", callback_data="event_qr:help")]
            ]
        ),
    )


@router.callback_query(F.data == "event_qr:help")
async def qr_help(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
) -> None:
    await call.answer()
    if not _approved(user) or not _can_manage_qr(user):
        await call.message.answer("QR вход доступен ответственным лидерам и администраторам.")
        return
    await _send_picker(call.message, user, session)


@router.message(Command("qr"), F.chat.type == "private")
async def qr_command(
    message: Message,
    command: CommandObject,
    user: User | None,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    if not _approved(user) or not _can_manage_qr(user):
        await message.answer("QR вход доступен ответственным лидерам и администраторам.")
        return
    if not command.args:
        await _send_picker(message, user, session)
        return
    try:
        event_id = int(command.args.strip())
    except ValueError:
        await message.answer("Используйте /qr или /qr <номер мероприятия>.")
        return
    event = await session.get(Event, event_id)
    if event is None or event.status not in CHECKIN_EVENT_STATUSES:
        await message.answer("Мероприятие не найдено или QR вход сейчас недоступен.")
        return
    await _generate(message, user, event, bot, settings)


@router.callback_query(F.data.startswith("event_qr:generate:"))
async def qr_generate(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    await call.answer()
    if not _approved(user) or not _can_manage_qr(user):
        return
    try:
        event_id = int(call.data.rsplit(":", 1)[-1])
    except (ValueError, AttributeError):
        return
    event = await session.get(Event, event_id)
    if event is None or event.status not in CHECKIN_EVENT_STATUSES:
        await call.message.answer("QR вход для этого мероприятия сейчас недоступен.")
        return
    await _generate(call.message, user, event, bot, settings)
