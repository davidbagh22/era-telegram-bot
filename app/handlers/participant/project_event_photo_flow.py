from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, Project, User
from app.services.audit_service import audit
from app.services.event_card import send_event_card, send_event_card_to_chat
from app.utils import texts
from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus
from app.utils.validators import clean_text, parse_date, parse_time

router = Router(name="participant_project_event_photo_flow")
SKIP_VALUES = {"-", "нет", "не нужно", "без", "без фото", "пропустить", "оставить"}


class ProjectEventStates(StatesGroup):
    event_date = State()
    event_time = State()
    location = State()
    format = State()
    participant_limit = State()
    points = State()
    chat_url = State()
    conditions = State()
    poster = State()
    preview = State()


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


async def _load_owned(session: AsyncSession, project_id: int, user: User) -> Project | None:
    project = await session.get(Project, project_id)
    return project if project and project.author_id == user.id else None


def _date_string(value) -> str | None:
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    parsed = parse_date(str(value or ""))
    return parsed.strftime("%d.%m.%Y") if parsed else None


def _time_string(value) -> str | None:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    parsed = parse_time(str(value or ""))
    return parsed.strftime("%H:%M") if parsed else None


def _additional_info(project_id: int, chat_url: str | None, conditions: str | None) -> str:
    lines = [f"[ERA_PROJECT_ID:{project_id}]"]
    if chat_url:
        lines.append(f"Чат мероприятия: {chat_url}")
    if conditions:
        lines.append(f"Условия участия: {conditions}")
    return "\n".join(lines)


def _event_preview_from_data(data: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=data.get("event_id", 0),
        title=data["event_title"],
        description=data["event_description"],
        event_date=parse_date(data["event_date"]),
        event_time=parse_time(data["event_time"]),
        location=data["event_location"],
        format=data["event_format"],
        participant_limit=data.get("event_limit"),
        points_for_visit=data.get("event_points", 0),
        poster_file_id=data.get("poster_file_id"),
        additional_info=_additional_info(
            int(data["project_id"]),
            data.get("event_chat_url"),
            data.get("event_conditions"),
        ),
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить на проверку", callback_data="project_event:confirm")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="project_event:cancel")],
        ]
    )


async def _ask_next(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("event_date"):
        await state.set_state(ProjectEventStates.event_date)
        await message.answer("Укажите дату мероприятия в формате ДД.ММ.ГГГГ.")
        return
    if not data.get("event_time"):
        await state.set_state(ProjectEventStates.event_time)
        await message.answer("Укажите время мероприятия в формате ЧЧ:ММ.")
        return
    if not data.get("event_location"):
        await state.set_state(ProjectEventStates.location)
        await message.answer("Укажите место проведения.")
        return
    if not data.get("event_format"):
        await state.set_state(ProjectEventStates.format)
        await message.answer("Укажите формат мероприятия: мастер-класс, игра, квест, встреча, кинопросмотр и т.д.")
        return
    if "event_limit" not in data:
        await state.set_state(ProjectEventStates.participant_limit)
        await message.answer("Укажите лимит участников числом. Если лимита нет, отправьте 0.")
        return
    if "event_points" not in data:
        await state.set_state(ProjectEventStates.points)
        await message.answer("Сколько баллов предусмотрено за подтверждённое участие?")
        return
    if "event_chat_url" not in data:
        await state.set_state(ProjectEventStates.chat_url)
        await message.answer("Отправьте ссылку на чат мероприятия. Если чата нет — напишите «нет».")
        return
    if "event_conditions" not in data:
        await state.set_state(ProjectEventStates.conditions)
        await message.answer("Укажите условия участия. Если условий нет — напишите «нет».")
        return
    if not data.get("poster_done"):
        await state.set_state(ProjectEventStates.poster)
        await message.answer("Отправьте фото/афишу мероприятия. Если пока без афиши — напишите «без фото».")
        return
    await state.set_state(ProjectEventStates.preview)
    await send_event_card(
        message,
        _event_preview_from_data(data),
        header="👁 Предпросмотр мероприятия",
        keyboard=_confirm_keyboard(),
    )


@router.callback_query(F.data.startswith("project:event:"))
async def project_event_start(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    project = await _load_owned(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project or project.status not in {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}:
        await call.message.answer("Оформить мероприятие можно после одобрения проекта")
        return
    existing = await session.scalar(select(Event).where(Event.project_id == project.id))
    if existing:
        await call.message.answer(f"Мероприятие уже создано: «{existing.title}»")
        return
    data = dict(project.form_data or {})
    await state.clear()
    await state.update_data(
        project_id=project.id,
        event_title=data.get("title") or project.title,
        event_description=data.get("announcement") or data.get("idea") or project.short_description,
        event_date=_date_string(data.get("proposed_date") or project.proposed_date),
        event_time=_time_string(data.get("proposed_time") or project.proposed_time),
        event_location=data.get("venue_request") or "",
        event_format=data.get("format") or project.format or "",
    )
    await call.message.answer(
        "📅 Оформляем мероприятие по одобренному проекту.\n\n"
        "Название и описание уже взяты из проекта. Сейчас уточним недостающие поля и афишу."
    )
    await _ask_next(call.message, state)


@router.message(ProjectEventStates.event_date)
async def project_event_date(message: Message, state: FSMContext) -> None:
    value = parse_date(message.text or "")
    if value is None:
        await message.answer("Проверьте дату. Формат: ДД.ММ.ГГГГ.")
        return
    await state.update_data(event_date=value.strftime("%d.%m.%Y"))
    await _ask_next(message, state)


@router.message(ProjectEventStates.event_time)
async def project_event_time(message: Message, state: FSMContext) -> None:
    value = parse_time(message.text or "")
    if value is None:
        await message.answer("Проверьте время. Формат: ЧЧ:ММ.")
        return
    await state.update_data(event_time=value.strftime("%H:%M"))
    await _ask_next(message, state)


@router.message(ProjectEventStates.location)
async def project_event_location(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(event_location=value)
    await _ask_next(message, state)


@router.message(ProjectEventStates.format)
async def project_event_format(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 100)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(event_format=value)
    await _ask_next(message, state)


@router.message(ProjectEventStates.participant_limit)
async def project_event_limit(message: Message, state: FSMContext) -> None:
    try:
        value = int(message.text or "")
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("Укажите целое число от 0.")
        return
    await state.update_data(event_limit=value or None)
    await _ask_next(message, state)


@router.message(ProjectEventStates.points)
async def project_event_points(message: Message, state: FSMContext) -> None:
    try:
        value = int(message.text or "")
        if not 0 <= value <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Укажите число от 0 до 1000.")
        return
    await state.update_data(event_points=value)
    await _ask_next(message, state)


@router.message(ProjectEventStates.chat_url)
async def project_event_chat(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 500)
    await state.update_data(event_chat_url="" if value.casefold() in SKIP_VALUES else value)
    await _ask_next(message, state)


@router.message(ProjectEventStates.conditions)
async def project_event_conditions(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 1000)
    await state.update_data(event_conditions="" if value.casefold() in SKIP_VALUES else value)
    await _ask_next(message, state)


@router.message(ProjectEventStates.poster)
async def project_event_poster(message: Message, state: FSMContext) -> None:
    if message.photo:
        await state.update_data(poster_file_id=message.photo[-1].file_id, poster_done=True)
        await _ask_next(message, state)
        return
    value = clean_text(message.text or "", 100).casefold()
    if value in SKIP_VALUES:
        await state.update_data(poster_file_id=None, poster_done=True)
        await _ask_next(message, state)
        return
    await message.answer("Отправьте изображение афиши или напишите «без фото».")


@router.callback_query(ProjectEventStates.preview, F.data == "project_event:cancel")
async def project_event_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await call.message.answer("Создание мероприятия отменено. Вернуться можно из раздела «Мои проекты».")


@router.callback_query(ProjectEventStates.preview, F.data == "project_event:confirm")
async def project_event_confirm(
    call: CallbackQuery,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
) -> None:
    await call.answer()
    data = await state.get_data()
    project = await _load_owned(session, int(data["project_id"]), user)
    if not project:
        await state.clear()
        await call.message.answer(texts.NO_ACCESS)
        return
    existing = await session.scalar(select(Event).where(Event.project_id == project.id))
    if existing:
        await state.clear()
        await call.message.answer(f"Мероприятие уже создано: «{existing.title}»")
        return
    event = Event(
        title=data["event_title"],
        description=data["event_description"],
        event_date=parse_date(data["event_date"]),
        event_time=parse_time(data["event_time"]),
        location=data["event_location"],
        format=data["event_format"],
        responsible_id=user.id,
        participant_limit=data.get("event_limit"),
        points_for_visit=data.get("event_points", 0),
        selfie_required=False,
        poster_file_id=data.get("poster_file_id"),
        additional_info=_additional_info(project.id, data.get("event_chat_url"), data.get("event_conditions")),
        status=EventStatus.PENDING_APPROVAL,
        created_by=user.id,
        project_id=project.id,
        department_id=project.department_id,
        direction_id=project.direction_id,
    )
    session.add(event)
    project.status = ProjectStatus.IN_PROGRESS
    await session.flush()
    await audit(session, actor_id=user.id, action="event.submitted_from_project", entity_type="event", entity_id=event.id)
    await state.clear()
    await call.message.answer(f"Мероприятие «{event.title}» отправлено администратору на проверку.")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть мероприятия", callback_data="admin:events")]])
    recipients = set(settings.admin_ids)
    if settings.leaders_chat_id:
        recipients.add(settings.leaders_chat_id)
    for chat_id in recipients:
        await send_event_card_to_chat(
            bot,
            chat_id,
            event,
            header=f"📅 Мероприятие из проекта #{project.id}",
            keyboard=keyboard,
        )
