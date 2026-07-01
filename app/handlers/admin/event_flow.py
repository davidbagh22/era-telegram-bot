from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventActivity, EventRegistration, User
from app.services.notification_service import safe_send
from app.utils import texts
from app.utils.constants import EVENT_STATUS_LABELS, EventStatus, Role

router = Router(name="admin_event_flow")


class EventEditStates(StatesGroup):
    announcement = State()


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(telegram_id in settings.admin_ids or (user and user.role == Role.ADMIN and not user.is_blocked))


async def _guard(event: Message | CallbackQuery, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    if not _is_admin(user, settings, telegram_id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def _event_keyboard(event: Event) -> InlineKeyboardMarkup:
    rows = []
    if event.status == EventStatus.PENDING_APPROVAL:
        rows.append([InlineKeyboardButton(text="✅ Утвердить", callback_data=f"admin:event:approve:{event.id}")])
        rows.append([InlineKeyboardButton(text="✏️ Изменить анонс", callback_data=f"admin:event:edit_text:{event.id}")])
        rows.append([InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:event:reject:{event.id}")])
    if event.status in {EventStatus.APPROVED, EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN}:
        rows.append([InlineKeyboardButton(text="📣 Подготовить рассылку 1/2", callback_data=f"admin:event:broadcast_prepare:{event.id}")])
        rows.append([InlineKeyboardButton(text="✨ Отправить задания участникам 1/2", callback_data=f"admin:event:tasks_prepare:{event.id}")])
    rows.append([InlineKeyboardButton(text="← События", callback_data="admin:menu:activity")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _event_text(event: Event) -> str:
    return (
        f"📅 Мероприятие #{event.id}\n\n"
        f"{event.title}\n\n"
        f"Дата: {event.event_date:%d.%m.%Y} в {event.event_time:%H:%M}\n"
        f"Место: {event.location}\n"
        f"Формат: {event.format}\n"
        f"Статус: {EVENT_STATUS_LABELS.get(event.status, event.status)}\n"
        f"Баллы за посещение: {event.points_for_visit}\n\n"
        f"Анонс:\n{event.description}"
    )


@router.callback_query(F.data == "admin:menu:activity")
async def activity_menu(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "📅 События и проекты\n\nЗдесь создаются мероприятия, утверждаются анонсы, рассылки и задания за баллы.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать мероприятие", callback_data="admin:event:new")],
                [InlineKeyboardButton(text="Мероприятия", callback_data="admin:events")],
                [InlineKeyboardButton(text="Проекты", callback_data="admin:projects")],
                [InlineKeyboardButton(text="Активности после мероприятий", callback_data="admin:event_activities")],
                [InlineKeyboardButton(text="Задания и конкурсы", callback_data="admin:tasks")],
                [InlineKeyboardButton(text="Назад", callback_data="admin:panel")],
            ]
        ),
    )


@router.callback_query(F.data == "admin:events")
async def events_list(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    events = (await session.scalars(select(Event).order_by(Event.event_date.desc(), Event.event_time).limit(50))).all()
    if not events:
        await call.message.answer("Мероприятий пока нет", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Создать", callback_data="admin:event:new")]]))
        return
    for event in events:
        await call.message.answer(_event_text(event), reply_markup=_event_keyboard(event))


@router.callback_query(F.data.startswith("admin:event:edit_text:"))
async def event_edit_text_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(EventEditStates.announcement)
    await state.update_data(edit_event_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer("Отправьте новый текст анонса")


@router.message(EventEditStates.announcement)
async def event_edit_text_save(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    event = await session.get(Event, int(data["edit_event_id"]))
    if not event:
        await state.clear()
        await message.answer("Мероприятие не найдено")
        return
    event.description = (message.text or message.caption or "").strip()[:4000]
    await state.clear()
    await message.answer("Анонс обновлён")


@router.callback_query(F.data.startswith("admin:event:approve:"))
async def event_approve(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        return
    event.status = EventStatus.APPROVED
    event.approved_by = user.id if user else None
    await call.message.answer(
        "Мероприятие утверждено. Рассылка ещё НЕ отправлена.\n\nДля отправки нажмите подготовку рассылки, затем финальное подтверждение.",
        reply_markup=_event_keyboard(event),
    )


@router.callback_query(F.data.startswith("admin:event:reject:"))
async def event_reject(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        return
    event.status = EventStatus.CANCELLED
    owner = await session.get(User, event.created_by)
    if owner:
        await safe_send(bot, owner.telegram_id, f"Мероприятие «{event.title}» не утверждено.")
    await call.message.answer("Мероприятие отклонено")


@router.callback_query(F.data.startswith("admin:event:broadcast_prepare:"))
async def event_broadcast_prepare(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        return
    await call.message.answer(
        "📣 Предпросмотр рассылки\n\n" + _event_text(event) + "\n\nФинальное подтверждение отправит анонс в общий чат.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📣 Отправить рассылку 2/2", callback_data=f"admin:event:broadcast_confirm:{event.id}")], [InlineKeyboardButton(text="✏️ Изменить анонс", callback_data=f"admin:event:edit_text:{event.id}")]]),
    )


@router.callback_query(F.data.startswith("admin:event:broadcast_confirm:"))
async def event_broadcast_confirm(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        return
    event.status = EventStatus.REGISTRATION_OPEN
    text = f"📅 {event.title}\n\n{event.description}\n\nДата: {event.event_date:%d.%m.%Y}\nВремя: {event.event_time:%H:%M}\nМесто: {event.location}"
    if settings.general_chat_id:
        if event.poster_file_id:
            try:
                await bot.send_photo(settings.general_chat_id, event.poster_file_id, caption=text)
            except Exception:
                await safe_send(bot, settings.general_chat_id, text)
        else:
            await safe_send(bot, settings.general_chat_id, text)
    await call.message.answer("Рассылка отправлена, если общий чат подключён. Регистрация открыта.")


@router.callback_query(F.data.startswith("admin:event:tasks_prepare:"))
async def event_tasks_prepare(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        return
    activities = (await session.scalars(select(EventActivity).where(EventActivity.event_id == event.id, EventActivity.is_active.is_(True)))).all()
    if not activities:
        await call.message.answer("У мероприятия нет заданий за баллы")
        return
    preview = "\n".join(f"• {a.title} · {a.points} баллов" for a in activities)
    await call.message.answer(
        f"✨ Задания для участников «{event.title}»\n\n{preview}\n\nФинальное подтверждение отправит задания всем зарегистрированным участникам.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✨ Отправить задания 2/2", callback_data=f"admin:event:tasks_confirm:{event.id}")]]),
    )


@router.callback_query(F.data.startswith("admin:event:tasks_confirm:"))
async def event_tasks_confirm(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(call, user, settings):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event:
        return
    activities = (await session.scalars(select(EventActivity).where(EventActivity.event_id == event.id, EventActivity.is_active.is_(True)))).all()
    registrations = (await session.scalars(select(EventRegistration).where(EventRegistration.event_id == event.id))).all()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{a.title} · {a.points} баллов", callback_data=f"event:activity:{a.id}")] for a in activities])
    sent = 0
    for registration in registrations:
        target = await session.get(User, registration.user_id)
        if target:
            await safe_send(bot, target.telegram_id, f"✨ Задания по мероприятию «{event.title}»\n\nВыберите задание, загрузите результат и вернитесь к списку.", reply_markup=keyboard)
            sent += 1
    await call.message.answer(f"Задания отправлены зарегистрированным участникам: {sent}")
