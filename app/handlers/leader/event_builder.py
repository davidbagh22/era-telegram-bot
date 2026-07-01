from datetime import datetime, time

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventActivity, User
from app.services.notification_service import notify_admins
from app.utils import texts
from app.utils.constants import EventStatus, PRIVILEGED_ROLES
from app.utils.validators import clean_text, parse_date, parse_time

router = Router(name="leader_event_builder")


class EventBuildStates(StatesGroup):
    title = State()
    text = State()
    poster = State()
    date = State()
    time = State()
    place = State()
    fmt = State()
    limit = State()
    points = State()
    tasks = State()


def _kb(callback: str = "event:build:cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отменить", callback_data=callback)]])


def _poster_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data="event:build:poster_skip")], [InlineKeyboardButton(text="Отменить", callback_data="event:build:cancel")]])


async def _guard(event: Message | CallbackQuery, user: User | None) -> bool:
    msg = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await event.answer()
    if not user or user.is_blocked or user.role not in PRIVILEGED_ROLES:
        await msg.answer(texts.NO_ACCESS)
        return False
    return True


@router.callback_query(F.data.in_({"leader:event:new", "admin:event:new"}))
async def event_start(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    if not await _guard(call, user):
        return
    await state.clear()
    await state.set_state(EventBuildStates.title)
    await call.message.answer("Название мероприятия", reply_markup=_kb())


@router.callback_query(F.data == "event:build:cancel")
async def event_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await call.message.answer("Создание мероприятия отменено")


@router.message(EventBuildStates.title)
async def event_title(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(title=value)
    await state.set_state(EventBuildStates.text)
    await message.answer("Текст анонса. Можно вставить готовый текст с эмодзи.", reply_markup=_kb())


@router.message(EventBuildStates.text)
async def event_text(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    value = clean_text(message.text or "", 4000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(text=value)
    await state.set_state(EventBuildStates.poster)
    await message.answer("Прикрепите афишу или пропустите", reply_markup=_poster_kb())


@router.callback_query(EventBuildStates.poster, F.data == "event:build:poster_skip")
async def poster_skip(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(poster=None)
    await state.set_state(EventBuildStates.date)
    await call.message.answer("Дата: ДД.ММ.ГГГГ", reply_markup=_kb())


@router.message(EventBuildStates.poster, F.photo | F.document)
async def poster_save(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    await state.update_data(poster=message.photo[-1].file_id if message.photo else message.document.file_id)
    await state.set_state(EventBuildStates.date)
    await message.answer("Дата: ДД.ММ.ГГГГ", reply_markup=_kb())


@router.message(EventBuildStates.date)
async def event_date(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    value = parse_date(message.text or "")
    if value is None:
        await message.answer("Проверьте дату. Пример: 15.07.2026")
        return
    await state.update_data(date=value.isoformat())
    await state.set_state(EventBuildStates.time)
    await message.answer("Время: ЧЧ:ММ", reply_markup=_kb())


@router.message(EventBuildStates.time)
async def event_time(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    value = parse_time(message.text or "")
    if value is None:
        await message.answer("Проверьте время. Пример: 18:30")
        return
    await state.update_data(time=value.strftime("%H:%M"))
    await state.set_state(EventBuildStates.place)
    await message.answer("Место", reply_markup=_kb())


@router.message(EventBuildStates.place)
async def event_place(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    value = clean_text(message.text or "", 255)
    await state.update_data(place=value)
    await state.set_state(EventBuildStates.fmt)
    await message.answer("Формат мероприятия", reply_markup=_kb())


@router.message(EventBuildStates.fmt)
async def event_fmt(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    await state.update_data(fmt=clean_text(message.text or "", 100) or "мероприятие")
    await state.set_state(EventBuildStates.limit)
    await message.answer("Лимит участников. 0 — без лимита", reply_markup=_kb())


@router.message(EventBuildStates.limit)
async def event_limit(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    try:
        value = int((message.text or "").strip())
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите число")
        return
    await state.update_data(limit=None if value == 0 else value)
    await state.set_state(EventBuildStates.points)
    await message.answer("Сколько баллов за посещение?", reply_markup=_kb())


@router.message(EventBuildStates.points)
async def event_points(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    try:
        value = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите число")
        return
    await state.update_data(points=max(0, min(value, 1000)))
    await state.set_state(EventBuildStates.tasks)
    await message.answer("Задания за баллы. Каждая строка: название | баллы | text/photo/video/file. Если нет — напишите -", reply_markup=_kb())


def _parse_tasks(raw: str):
    if raw.strip() == "-":
        return []
    items = []
    for line in raw.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            try:
                points = int(parts[1])
            except ValueError:
                points = 0
            kind = parts[2] if parts[2] in {"text", "photo", "video", "file"} else "text"
            items.append((parts[0][:255], max(0, min(points, 1000)), kind))
    return items


@router.message(EventBuildStates.tasks)
async def event_finish(message: Message, user: User | None, state: FSMContext, session: AsyncSession, bot: Bot, settings: Settings) -> None:
    if not await _guard(message, user):
        return
    data = await state.get_data()
    event = Event(
        title=data["title"],
        description=data["text"],
        event_date=datetime.fromisoformat(data["date"]).date(),
        event_time=time.fromisoformat(data["time"]),
        location=data["place"],
        format=data["fmt"],
        participant_limit=data.get("limit"),
        points_for_visit=data["points"],
        poster_file_id=data.get("poster"),
        additional_info="activities:manual_send",
        status=EventStatus.PENDING_APPROVAL,
        created_by=user.id,
        responsible_id=user.id,
    )
    session.add(event)
    await session.flush()
    for title, points, kind in _parse_tasks(message.text or ""):
        session.add(EventActivity(event_id=event.id, title=title, description="Отправьте результат по заданию в боте", submission_type=kind, points=points, is_active=True))
    await state.clear()
    await message.answer("Мероприятие отправлено админу на утверждение.")
    await notify_admins(bot, settings, f"📅 Новое мероприятие на утверждении\n\n{event.title}\n{event.event_date:%d.%m.%Y} в {event.event_time:%H:%M}\nМесто: {event.location}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть мероприятия", callback_data="admin:events")]]))
