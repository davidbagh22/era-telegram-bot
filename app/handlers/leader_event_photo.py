from __future__ import annotations

from types import SimpleNamespace

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Department, Direction, Event, User
from app.services.audit_service import audit
from app.services.event_card import send_event_card, send_event_card_to_chat
from app.states.event import EventStates
from app.utils import texts
from app.utils.constants import EventStatus
from app.utils.validators import clean_text

router = Router(name="leader_event_photo")
SKIP_VALUES = {"-", "нет", "не нужно", "без", "без фото", "пропустить"}


class LeaderEventPhotoStates(StatesGroup):
    chat_url = State()
    conditions = State()
    poster = State()
    preview = State()


def _additional_info(data: dict) -> str:
    lines = []
    if data.get("event_ai_plan"):
        lines.append(str(data["event_ai_plan"]))
    if data.get("event_chat_url"):
        lines.append(f"Чат мероприятия: {data['event_chat_url']}")
    if data.get("event_conditions"):
        lines.append(f"Условия участия: {data['event_conditions']}")
    return "\n".join(lines) or ""


def _preview_event(data: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=0,
        title=data["event_title"],
        description=data["event_description"],
        event_date=data["event_date"],
        event_time=data["event_time"],
        location=data["event_location"],
        format=data["event_format"],
        participant_limit=data.get("event_limit"),
        points_for_visit=data.get("event_points", 0),
        poster_file_id=data.get("poster_file_id"),
        additional_info=_additional_info(data),
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить на проверку", callback_data="leader_event:confirm")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="leader_event:cancel")],
        ]
    )


async def _ask_preview(message: Message, state: FSMContext) -> None:
    await state.set_state(LeaderEventPhotoStates.preview)
    data = await state.get_data()
    await send_event_card(
        message,
        _preview_event(data),
        header="👁 Предпросмотр мероприятия",
        keyboard=_confirm_keyboard(),
    )


@router.message(EventStates.points)
async def event_points_with_poster(message: Message, state: FSMContext) -> None:
    try:
        value = int(message.text or "")
        if not 0 <= value <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Укажите число от 0 до 1000.")
        return
    await state.update_data(event_points=value)
    await state.set_state(LeaderEventPhotoStates.chat_url)
    await message.answer("Отправьте ссылку на чат мероприятия. Если чата нет — напишите «нет».")


@router.message(LeaderEventPhotoStates.chat_url)
async def event_chat_url(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 500)
    await state.update_data(event_chat_url="" if value.casefold() in SKIP_VALUES else value)
    await state.set_state(LeaderEventPhotoStates.conditions)
    await message.answer("Укажите условия участия. Если условий нет — напишите «нет».")


@router.message(LeaderEventPhotoStates.conditions)
async def event_conditions(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 1000)
    await state.update_data(event_conditions="" if value.casefold() in SKIP_VALUES else value)
    await state.set_state(LeaderEventPhotoStates.poster)
    await message.answer("Отправьте фото/афишу мероприятия. Если пока без афиши — напишите «без фото».")


@router.message(LeaderEventPhotoStates.poster)
async def event_poster(message: Message, state: FSMContext) -> None:
    if message.photo:
        await state.update_data(poster_file_id=message.photo[-1].file_id)
        await _ask_preview(message, state)
        return
    value = clean_text(message.text or "", 100).casefold()
    if value in SKIP_VALUES:
        await state.update_data(poster_file_id=None)
        await _ask_preview(message, state)
        return
    await message.answer("Отправьте изображение афиши или напишите «без фото».")


@router.callback_query(LeaderEventPhotoStates.preview, F.data == "leader_event:cancel")
async def event_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await call.message.answer("Создание мероприятия отменено.")


@router.callback_query(LeaderEventPhotoStates.preview, F.data == "leader_event:confirm")
async def event_confirm(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    await call.answer()
    data = await state.get_data()
    department = await session.scalar(select(Department).where(Department.name == data["event_department"]))
    direction = await session.scalar(select(Direction).where(Direction.name == data["event_direction"]))
    if not department or not direction:
        await call.message.answer("Не удалось найти департамент или направление. Начните создание мероприятия заново.")
        await state.clear()
        return
    event = Event(
        title=data["event_title"],
        description=data["event_description"],
        event_date=data["event_date"],
        event_time=data["event_time"],
        location=data["event_location"],
        department_id=department.id,
        direction_id=direction.id,
        format=data["event_format"],
        responsible_id=user.id,
        participant_limit=data.get("event_limit"),
        points_for_visit=data.get("event_points", 0),
        selfie_required=False,
        poster_file_id=data.get("poster_file_id"),
        additional_info=_additional_info(data),
        status=EventStatus.PENDING_APPROVAL,
        created_by=user.id,
    )
    session.add(event)
    await session.flush()
    await audit(session, actor_id=user.id, action="event.submitted", entity_type="event", entity_id=event.id)
    await state.clear()
    await call.message.answer(
        "Мероприятие отправлено администратору на утверждение.\n\n"
        "Фото/афиша сохранены и будут отображаться в карточке мероприятия."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть мероприятия", callback_data="admin:events")]])
    for chat_id in set(settings.admin_ids):
        await send_event_card_to_chat(bot, chat_id, event, header="📅 Мероприятие на утверждении", keyboard=keyboard)
