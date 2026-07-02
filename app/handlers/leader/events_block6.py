from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, User
from app.services.audit_service import audit
from app.services.notification_service import notify_admins
from app.utils import texts
from app.utils.constants import EventStatus, PRIVILEGED_ROLES
from app.utils.validators import clean_text, parse_date, parse_time

router = Router(name="leader_events_block6")


class EventBlock6States(StatesGroup):
    title = State()
    description = State()
    date = State()
    time = State()
    location = State()
    format = State()
    limit = State()
    points = State()
    poster = State()
    ready_text = State()


def is_leader(user: User | None) -> bool:
    return bool(user and not user.is_blocked and user.role in PRIVILEGED_ROLES)


async def guard(event: CallbackQuery | Message, user: User | None) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
    else:
        message = event
    if not is_leader(user):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Конструктор по шагам", callback_data="leader:event6:mode:constructor")],
        [InlineKeyboardButton(text="📝 Готовый анонс + фото", callback_data="leader:event6:mode:ready")],
        [InlineKeyboardButton(text="← Панель", callback_data="leader:panel")],
    ])


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить фото", callback_data="leader:event6:poster:skip")]])


@router.callback_query(F.data.startswith("leader:event:revise:"))
async def event_revise(call: CallbackQuery, user: User | None, state: FSMContext, session: AsyncSession) -> None:
    if not await guard(call, user):
        return
    event = await session.get(Event, int(call.data.rsplit(":", 1)[-1]))
    if not event or event.created_by != user.id or event.status != EventStatus.DRAFT:
        await call.message.answer(texts.NO_ACCESS)
        return
    await state.clear()
    await state.update_data(event_mode="constructor", editing_event_id=event.id)
    await state.set_state(EventBlock6States.title)
    await call.message.answer(f"Исправляем «{event.title}». Введите итоговое название заново.")


@router.callback_query(F.data == "leader:event:new")
async def event_new(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    if not await guard(call, user):
        return
    await state.clear()
    await call.message.answer("Как подготовить мероприятие?", reply_markup=mode_keyboard())


@router.callback_query(F.data.startswith("leader:event6:mode:"))
async def mode(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    if not await guard(call, user):
        return
    mode_value = call.data.rsplit(":", 1)[-1]
    await state.update_data(event_mode=mode_value)
    await state.set_state(EventBlock6States.title)
    await call.message.answer("Напишите короткое название мероприятия.")


@router.message(EventBlock6States.title)
async def title(message: Message, user: User | None, state: FSMContext) -> None:
    if not await guard(message, user):
        return
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(title=value)
    data = await state.get_data()
    if data.get("event_mode") == "ready":
        await state.set_state(EventBlock6States.ready_text)
        await message.answer("Вставьте готовый текст анонса. Можно вместе с фото — отправьте фото с подписью.")
    else:
        await state.set_state(EventBlock6States.description)
        await message.answer("Напишите описание мероприятия / анонс.")


@router.message(EventBlock6States.ready_text)
async def ready_text(message: Message, user: User | None, state: FSMContext) -> None:
    if not await guard(message, user):
        return
    text = clean_text(message.text or message.caption or "", 3000)
    if not text:
        await message.answer("Нужен текст анонса")
        return
    poster = message.photo[-1].file_id if message.photo else None
    await state.update_data(description=text, poster=poster)
    await state.set_state(EventBlock6States.date)
    await message.answer("Укажите дату мероприятия: ДД.ММ.ГГГГ")


@router.message(EventBlock6States.description)
async def description(message: Message, user: User | None, state: FSMContext) -> None:
    if not await guard(message, user):
        return
    value = clean_text(message.text or "", 3000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(description=value)
    await state.set_state(EventBlock6States.date)
    await message.answer("Укажите дату: ДД.ММ.ГГГГ")


@router.message(EventBlock6States.date)
async def date_step(message: Message, user: User | None, state: FSMContext) -> None:
    if not await guard(message, user):
        return
    value = parse_date(message.text or "")
    if value is None:
        await message.answer("Проверьте формат: ДД.ММ.ГГГГ")
        return
    await state.update_data(date=value)
    await state.set_state(EventBlock6States.time)
    await message.answer("Укажите время: ЧЧ:ММ")


@router.message(EventBlock6States.time)
async def time_step(message: Message, user: User | None, state: FSMContext) -> None:
    if not await guard(message, user):
        return
    value = parse_time(message.text or "")
    if value is None:
        await message.answer("Проверьте формат: ЧЧ:ММ")
        return
    await state.update_data(time=value)
    await state.set_state(EventBlock6States.location)
    await message.answer("Укажите место проведения.")


@router.message(EventBlock6States.location)
async def location(message: Message, user: User | None, state: FSMContext) -> None:
    if not await guard(message, user):
        return
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(location=value)
    await state.set_state(EventBlock6States.format)
    await message.answer("Укажите формат: мастер-класс, игра, встреча, экскурсия и т.д.")


@router.message(EventBlock6States.format)
async def format_step(message: Message, user: User | None, state: FSMContext) -> None:
    if not await guard(message, user):
        return
    value = clean_text(message.text or "", 100)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(format=value)
    await state.set_state(EventBlock6States.limit)
    await message.answer("Лимит участников числом. Если лимита нет — 0.")


@router.message(EventBlock6States.limit)
async def limit_step(message: Message, user: User | None, state: FSMContext) -> None:
    if not await guard(message, user):
        return
    try:
        value = int((message.text or "").strip())
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 0")
        return
    await state.update_data(limit=value or None)
    await state.set_state(EventBlock6States.points)
    await message.answer("Сколько баллов за подтверждённое участие? От 0 до 1000.")


@router.message(EventBlock6States.points)
async def points_step(message: Message, user: User | None, state: FSMContext, session: AsyncSession, bot: Bot, settings: Settings) -> None:
    if not await guard(message, user):
        return
    try:
        value = int((message.text or "").strip())
        if not 0 <= value <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 0 до 1000")
        return
    await state.update_data(points=value)
    data = await state.get_data()
    if data.get("poster"):
        await finish_event(message, user, state, session, bot, settings)
        return
    await state.set_state(EventBlock6States.poster)
    await message.answer("Прикрепите афишу/фото или нажмите «Пропустить фото».", reply_markup=skip_keyboard())


@router.callback_query(EventBlock6States.poster, F.data == "leader:event6:poster:skip")
async def skip_poster(call: CallbackQuery, user: User | None, state: FSMContext, session: AsyncSession, bot: Bot, settings: Settings) -> None:
    if not await guard(call, user):
        return
    await finish_event(call.message, user, state, session, bot, settings)


@router.message(EventBlock6States.poster)
async def poster_step(message: Message, user: User | None, state: FSMContext, session: AsyncSession, bot: Bot, settings: Settings) -> None:
    if not await guard(message, user):
        return
    poster = message.photo[-1].file_id if message.photo else None
    if not poster:
        await message.answer("Отправьте фото или нажмите «Пропустить фото».", reply_markup=skip_keyboard())
        return
    await state.update_data(poster=poster)
    await finish_event(message, user, state, session, bot, settings)


async def finish_event(message: Message, user: User, state: FSMContext, session: AsyncSession, bot: Bot, settings: Settings) -> None:
    data = await state.get_data()
    event = await session.get(Event, int(data["editing_event_id"])) if data.get("editing_event_id") else None
    if event is None:
        event = Event(created_by=user.id, responsible_id=user.id)
        session.add(event)
    event.title = data["title"]
    event.description = data["description"]
    event.event_date = data["date"]
    event.event_time = data["time"]
    event.location = data["location"]
    event.format = data["format"]
    event.participant_limit = data.get("limit")
    event.points_for_visit = data.get("points", 0)
    event.selfie_required = False
    event.poster_file_id = data.get("poster")
    event.status = EventStatus.PENDING_APPROVAL
    await session.flush()
    await audit(session, actor_id=user.id, action="event.submitted.block6", entity_type="event", entity_id=event.id)
    await state.clear()
    await message.answer("Мероприятие отправлено админу на утверждение. Рассылка не уйдёт без двойного подтверждения админа.")
    await notify_admins(bot, settings, f"📅 Мероприятие на утверждении\n\n#{event.id} {event.title}\n\nДата: {event.event_date:%d.%m.%Y} {event.event_time:%H:%M}\nМесто: {event.location}")
