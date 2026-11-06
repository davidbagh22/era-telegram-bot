import logging

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.general_topics_service import send_general_topic_once
from app.database.models import Event, User
from app.services import event_moderation_service
from app.services.audit_service import audit
from app.services.authorization_service import can_manage_events
from app.services.event_card import format_event_text, send_event_card
from app.services.event_publication_service import escaped_text_parts
from app.services.notification_service import safe_send, safe_answer_photo
from app.utils import texts
from app.utils.constants import EVENT_STATUS_LABELS, EventStatus
from app.utils.deep_links import telegram_event_miniapp_url
from app.utils.validators import clean_text

router = Router(name="admin_events_block6")
PREPARED_MARK = "[ERA_BROADCAST_PREPARED]"
logger = logging.getLogger(__name__)


class EventDecisionStates(StatesGroup):
    comment = State()


def is_admin(user: User | None, settings: Settings, tg_id: int) -> bool:
    return can_manage_events(user, settings, tg_id)


async def guard(call: CallbackQuery, user: User | None, settings: Settings) -> bool:
    await call.answer()
    if not is_admin(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return False
    return True


def public_text(event: Event) -> str:
    return format_event_text(
        event,
        header="📅 Новое мероприятие ЭРА",
        extra_text="Регистрация открыта в боте.",
    )


async def public_event_keyboard(
    bot: Bot, settings: Settings, event: Event
) -> InlineKeyboardMarkup | None:
    """Group-safe direct link to the exact event screen in the Main Mini App."""
    username = (settings.bot_username or "").strip()
    if not username:
        me = await bot.get_me()
        username = me.username or ""
    url = telegram_event_miniapp_url(username, event.id)
    if not url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть мероприятие", url=url)]
        ]
    )


def event_kb(event: Event, *, settings: Settings | None = None, telegram_id: int = 0) -> InlineKeyboardMarkup:
    rows = []
    if event.status == EventStatus.PENDING_APPROVAL:
        rows.append([InlineKeyboardButton(text="✅ Одобрить без рассылки", callback_data=f"admin:event:approve:{event.id}")])
        rows.append([InlineKeyboardButton(text="✏️ На доработку", callback_data=f"admin:event:revise:{event.id}")])
        rows.append([InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:event:reject:{event.id}")])
    elif event.status == EventStatus.APPROVED:
        rows.append([InlineKeyboardButton(text="👁 Предпросмотр рассылки", callback_data=f"admin:event:broadcast_preview:{event.id}")])
        rows.append([InlineKeyboardButton(text="✅ Подготовить рассылку 1/2", callback_data=f"admin:event:broadcast_prepare:{event.id}")])
    elif event.status in {EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN, EventStatus.REGISTRATION_CLOSED, EventStatus.ACTIVE, EventStatus.COMPLETED}:
        rows.append([InlineKeyboardButton(text="👥 Участники и посещение", callback_data=f"admin:event:participants:{event.id}")])
        if event.status == EventStatus.PUBLISHED:
            rows.append([InlineKeyboardButton(text="🟢 Открыть регистрацию", callback_data=f"admin:event:status:registration_open:{event.id}")])
        elif event.status == EventStatus.REGISTRATION_OPEN:
            rows.append([InlineKeyboardButton(text="🔒 Закрыть регистрацию", callback_data=f"admin:event:status:registration_closed:{event.id}")])
            rows.append([InlineKeyboardButton(text="▶️ Мероприятие началось", callback_data=f"admin:event:status:active:{event.id}")])
        elif event.status == EventStatus.REGISTRATION_CLOSED:
            rows.append([InlineKeyboardButton(text="▶️ Мероприятие началось", callback_data=f"admin:event:status:active:{event.id}")])
        elif event.status == EventStatus.ACTIVE:
            rows.append([InlineKeyboardButton(text="🏁 Завершить мероприятие", callback_data=f"admin:event:status:completed:{event.id}")])
        elif event.status == EventStatus.COMPLETED:
            rows.append([InlineKeyboardButton(text="➕ Создать активности", callback_data=f"admin:event:activities:create:{event.id}")])
            rows.append([InlineKeyboardButton(text="📤 Отправить активности", callback_data=f"admin:event:activities:send:{event.id}")])
            rows.append([InlineKeyboardButton(text="📥 Активности на проверке", callback_data="admin:event_activities:review")])
    from app.services.event_attendance_service import attendance_v2_enabled
    if settings and attendance_v2_enabled(settings, telegram_id) and event.status in {EventStatus.COMPLETED, EventStatus.REPORT_SUBMITTED}:
        rows.append([InlineKeyboardButton(text="📷 QR подтверждения посещения", callback_data=f"admin:event:confirm_qr:{event.id}")])
        rows.append([InlineKeyboardButton(text="🔒 Закрыть подтверждение посещения", callback_data=f"admin:event:close_confirmation:{event.id}")])
    rows.append([InlineKeyboardButton(text="← События", callback_data="admin:menu:activity")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:events")
async def events_list(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await guard(call, user, settings):
        return
    await call.message.answer("📅 Управление мероприятиями", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Создать мероприятие", callback_data="leader:event:new")]]))
    events = (await session.scalars(select(Event).order_by(Event.event_date.desc(), Event.event_time).limit(50))).all()
    if not events:
        await call.message.answer("Мероприятий пока нет")
        return
    for event in events:
        await send_event_card(
            call.message,
            event,
            header=f"📅 Мероприятие #{event.id}\nСтатус: {EVENT_STATUS_LABELS.get(event.status, event.status)}",
            keyboard=event_kb(event, settings=settings, telegram_id=call.from_user.id),
        )


@router.callback_query(F.data.startswith("admin:event:approve:"))
async def approve_event(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        await call.message.answer("Мероприятие не найдено")
        return
    result = await event_moderation_service.decide_event(
        session, event, action="approve", comment="", actor=user
    )
    if result.owner:
        await safe_send(bot, result.owner.telegram_id, result.notice)
    await send_event_card(
        call.message,
        event,
        header="Мероприятие одобрено. Рассылка ещё не отправлена.",
        keyboard=event_kb(event, settings=settings, telegram_id=call.from_user.id),
    )


@router.callback_query(F.data.startswith("admin:event:broadcast_preview:"))
async def broadcast_preview(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        await call.message.answer("Мероприятие не найдено")
        return
    await send_event_card(
        call.message,
        event,
        header="👁 Предпросмотр рассылки",
        extra_text="Регистрация будет открыта в боте после публикации.",
        keyboard=event_kb(event, settings=settings, telegram_id=call.from_user.id),
    )


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


async def _deliver_prepared_announcement(bot: Bot, settings: Settings, event: Event) -> str:
    """Durable legacy announcement: same key on every admin retry/restart.

    Never accept an unconfirmed Telegram acknowledgement as successful.
    Already-sent parts are reused from the receipt ledger; an uncertain
    outcome blocks replay until an operator reconciles it.
    """
    poster = getattr(event, "poster_file_id", None)
    text = format_event_text(
        event, header="🔥 Новое событие ЭРА",
        extra_text="Регистрация откроется в боте после публикации.",
    )
    parts = escaped_text_parts(text, 1000 if poster else 4000)
    keyboard = await public_event_keyboard(bot, settings, event)
    for index, part in enumerate(parts):
        result = await send_general_topic_once(
            bot, settings, "announcements", part,
            delivery_key=f"legacy-event:{event.id}:broadcast:part:{index}",
            parse_mode="HTML", max_attempts=1,
            reply_markup=keyboard if index == len(parts) - 1 else None,
            photo=poster if index == 0 else None,
        )
        if result.status != "sent":
            return result.status
    return "sent"


@router.callback_query(F.data.startswith("admin:event:broadcast_publish:"))
async def broadcast_publish(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event or PREPARED_MARK not in (event.additional_info or ""):
        await call.message.answer("Сначала нажмите «Подготовить рассылку 1/2»")
        return

    if event.status != EventStatus.APPROVED:
        await call.message.answer("Рассылка недоступна для текущего статуса мероприятия.")
        return

    # The registration state is committed only after every part has a durable
    # Telegram acknowledgement. If delivery fails or is uncertain, the
    # prepared marker remains, allowing an admin to retry the SAME keys safely.
    try:
        delivery_status = await _deliver_prepared_announcement(bot, settings, event)
    except Exception:
        logger.exception("Legacy event announcement failed event_id=%s", event.id)
        delivery_status = "failed"

    if delivery_status != "sent":
        await call.message.answer(
            "Анонс не подтверждён, регистрация не открыта. "
            "При ошибке сети или частичной доставке сначала сверьте сообщения "
            "в теме «Мероприятия». Повтор использует прежние ключи доставки; "
            "неподтверждённые сообщения автоматически не дублируются."
        )
        return

    event.status = EventStatus.REGISTRATION_OPEN
    event.additional_info = (event.additional_info or "").replace(PREPARED_MARK, "").strip()
    await session.commit()
    await audit(session, actor_id=user.id if user else None,
                action="event.broadcast_published", entity_type="event", entity_id=event.id)
    await call.message.answer(
        "Регистрация открыта. Доставка анонса подтверждена.",
        reply_markup=event_kb(event, settings=settings, telegram_id=call.from_user.id),
    )


@router.callback_query(F.data.regexp(r"^admin:event:(revise|reject):\d+$"))
async def event_decision_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await guard(call, user, settings):
        return
    _, _, action, raw_id = call.data.split(":")
    await state.set_state(EventDecisionStates.comment)
    await state.update_data(event_decision_action=action, event_decision_id=int(raw_id))
    await call.message.answer("Напишите комментарий автору")


@router.message(EventDecisionStates.comment)
async def event_decision_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not is_admin(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return
    comment = clean_text(message.text or "", 2000)
    if not comment:
        await message.answer("Комментарий обязателен")
        return
    data = await state.get_data()
    event = await session.get(Event, int(data["event_decision_id"]))
    if not event:
        await state.clear()
        return
    action = data["event_decision_action"]
    result = await event_moderation_service.decide_event(
        session, event, action=action, comment=comment, actor=user
    )
    if result.owner:
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✏️ Исправить мероприятие", callback_data=f"leader:event:revise:{event.id}")
        ]]) if action == "revise" else None
        await safe_send(bot, result.owner.telegram_id, result.notice, reply_markup=markup)
    await state.clear()
    await message.answer("Решение сохранено")


@router.callback_query(F.data.regexp(r"^admin:event:confirm_qr:[0-9]+$"), F.message.chat.type == "private")
async def event_confirmation_qr(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession):
    if not await guard(call, user, settings):
        return
    if not user or user.is_blocked or user.is_archived:
        return
    from aiogram.types import BufferedInputFile
    from app.services.event_attendance_service import confirmation_qr
    event_id = int(call.data.rsplit(':', 1)[-1])
    try:
        _link, image = await confirmation_qr(session, event_id, settings=settings, telegram_id=call.from_user.id)
    except ValueError:
        await call.message.answer('QR доступен ведущему после завершения мероприятия, пока открыто подтверждение посещения.')
        return
    from html import escape
    event = await session.get(Event, event_id)
    await safe_answer_photo(call.message, BufferedInputFile(image, filename=f'ERA-attendance-{event_id}.png'),
        caption=f"Посещение: {escape(event.title)}\n\n" + 'Покажите QR участникам, которые присутствовали. Подтверждение откроется в личном боте. Повторное сканирование не начисляет баллы повторно.')


@router.callback_query(F.data.regexp(r"^admin:event:close_confirmation:[0-9]+$"), F.message.chat.type == "private")
async def event_close_confirmation(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession):
    if not await guard(call, user, settings) or not user or user.is_blocked or user.is_archived:
        return
    from app.services.event_attendance_service import attendance_v2_enabled, close_confirmation
    if not attendance_v2_enabled(settings, call.from_user.id):
        return
    try:
        await close_confirmation(session, int(call.data.rsplit(':', 1)[-1]), actor_user_id=user.id)
    except ValueError:
        await call.message.answer('Окно подтверждения сейчас недоступно.')
        return
    await session.commit()
    await call.message.answer('Подтверждение закрыто. Сохранённые посещения и баллы остаются в истории.')
