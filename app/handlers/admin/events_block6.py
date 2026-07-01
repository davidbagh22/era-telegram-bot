from aiogram import F, Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, User
from app.services.audit_service import audit
from app.services.notification_service import safe_send
from app.utils import texts
from app.utils.constants import EVENT_STATUS_LABELS, EventStatus, Role

router = Router(name="admin_events_block6")
PREPARED_MARK = "[ERA_BROADCAST_PREPARED]"


def is_admin(user: User | None, settings: Settings, tg_id: int) -> bool:
    return bool(tg_id in settings.admin_ids or (user and user.role == Role.ADMIN and not user.is_blocked))


async def guard(call: CallbackQuery, user: User | None, settings: Settings) -> bool:
    await call.answer()
    if not is_admin(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return False
    return True


def public_text(event: Event) -> str:
    return (
        f"📅 Новое мероприятие ЭРА\n\n"
        f"{event.title}\n\n"
        f"{event.description}\n\n"
        f"Дата: {event.event_date:%d.%m.%Y}\n"
        f"Время: {event.event_time:%H:%M}\n"
        f"Место: {event.location}\n"
        f"Формат: {event.format}\n\n"
        "Регистрация открыта в боте."
    )


def event_kb(event: Event) -> InlineKeyboardMarkup:
    rows = []
    if event.status == EventStatus.PENDING_APPROVAL:
        rows.append([InlineKeyboardButton(text="✅ Одобрить без рассылки", callback_data=f"admin:event:approve:{event.id}")])
        rows.append([InlineKeyboardButton(text="✏️ На доработку", callback_data=f"admin:event:revise:{event.id}")])
        rows.append([InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:event:reject:{event.id}")])
    elif event.status == EventStatus.APPROVED:
        rows.append([InlineKeyboardButton(text="👁 Предпросмотр рассылки", callback_data=f"admin:event:broadcast_preview:{event.id}")])
        rows.append([InlineKeyboardButton(text="✅ Подготовить рассылку 1/2", callback_data=f"admin:event:broadcast_prepare:{event.id}")])
    elif event.status in {EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN, EventStatus.COMPLETED}:
        rows.append([InlineKeyboardButton(text="👥 Участники и посещение", callback_data=f"admin:event:participants:{event.id}")])
        rows.append([InlineKeyboardButton(text="➕ Создать активности", callback_data=f"admin:event:activities:create:{event.id}")])
        rows.append([InlineKeyboardButton(text="📤 Отправить активности", callback_data=f"admin:event:activities:send:{event.id}")])
        rows.append([InlineKeyboardButton(text="📥 Активности на проверке", callback_data="admin:event_activities:review")])
    rows.append([InlineKeyboardButton(text="← События", callback_data="admin:menu:activity")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:events")
async def events_list(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await guard(call, user, settings):
        return
    events = (await session.scalars(select(Event).order_by(Event.event_date.desc(), Event.event_time).limit(50))).all()
    if not events:
        await call.message.answer("Мероприятий пока нет")
        return
    for event in events:
        await call.message.answer(
            f"📅 Мероприятие #{event.id}\n\n{event.title}\n\n"
            f"{event.event_date:%d.%m.%Y} в {event.event_time:%H:%M}\n"
            f"Место: {event.location}\n"
            f"Статус: {EVENT_STATUS_LABELS.get(event.status, event.status)}",
            reply_markup=event_kb(event),
        )


@router.callback_query(F.data.startswith("admin:event:approve:"))
async def approve_event(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        await call.message.answer("Мероприятие не найдено")
        return
    event.status = EventStatus.APPROVED
    event.approved_by = user.id if user else None
    await audit(session, actor_id=user.id if user else None, action="event.approved_without_broadcast", entity_type="event", entity_id=event.id)
    owner = await session.get(User, event.created_by)
    if owner:
        await safe_send(bot, owner.telegram_id, f"Мероприятие «{event.title}» одобрено. Рассылка будет только после отдельного подтверждения админа.")
    await call.message.answer("Мероприятие одобрено. Рассылка ещё не отправлена.", reply_markup=event_kb(event))


@router.callback_query(F.data.startswith("admin:event:broadcast_preview:"))
async def broadcast_preview(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        await call.message.answer("Мероприятие не найдено")
        return
    await call.message.answer(f"👁 Предпросмотр рассылки\n\n{public_text(event)}", reply_markup=event_kb(event))


@router.callback_query(F.data.startswith("admin:event:broadcast_prepare:"))
async def broadcast_prepare(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event or event.status != EventStatus.APPROVED:
        await call.message.answer("Сначала мероприятие должно быть одобрено")
        return
    info = event.additional_info or ""
    if PREPARED_MARK not in info:
        event.additional_info = (info + "\n" + PREPARED_MARK).strip()
    await call.message.answer(
        "Рассылка подготовлена. Следующее нажатие отправит анонс в общий чат и откроет регистрацию.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📣 Отправить рассылку 2/2", callback_data=f"admin:event:broadcast_publish:{event.id}")],
            [InlineKeyboardButton(text="👁 Ещё раз предпросмотр", callback_data=f"admin:event:broadcast_preview:{event.id}")],
        ]),
    )


@router.callback_query(F.data.startswith("admin:event:broadcast_publish:"))
async def broadcast_publish(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event or PREPARED_MARK not in (event.additional_info or ""):
        await call.message.answer("Сначала нажмите «Подготовить рассылку 1/2»")
        return
    text = public_text(event)
    if settings.general_chat_id:
        if event.poster_file_id:
            try:
                await bot.send_photo(settings.general_chat_id, event.poster_file_id, caption=text)
            except Exception:
                await safe_send(bot, settings.general_chat_id, text)
        else:
            await safe_send(bot, settings.general_chat_id, text)
    event.status = EventStatus.REGISTRATION_OPEN
    event.additional_info = (event.additional_info or "").replace(PREPARED_MARK, "").strip()
    await audit(session, actor_id=user.id if user else None, action="event.broadcast_published", entity_type="event", entity_id=event.id)
    await call.message.answer("Рассылка отправлена, регистрация открыта.", reply_markup=event_kb(event))
