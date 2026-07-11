from __future__ import annotations

from datetime import date, time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, Project, User
from app.services.audit_service import audit
from app.services.notification_service import notify_admins
from app.utils import texts
from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus
from app.utils.validators import clean_text, parse_date, parse_time

router = Router(name="participant_project_event_flow")


class ProjectEventStates(StatesGroup):
    date = State()
    time = State()
    location = State()
    format = State()
    participant_limit = State()
    points = State()


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


async def _load_owned_project(
    session: AsyncSession, project_id: int, user: User
) -> Project | None:
    project = await session.get(Project, project_id)
    return project if project and project.author_id == user.id else None


def _parse_project_date(project: Project) -> date | None:
    if project.proposed_date:
        return project.proposed_date
    raw = (project.form_data or {}).get("proposed_date")
    return parse_date(str(raw or ""))


def _parse_project_time(project: Project) -> time | None:
    if project.proposed_time:
        return project.proposed_time
    raw = (project.form_data or {}).get("proposed_time")
    return parse_time(str(raw or ""))


def _clean_project_value(value: object) -> str | None:
    text = clean_text(str(value or ""), 500)
    if not text or text.lower() in {"нет", "не указано", "не указана", "-"}:
        return None
    return text


def _first_department_id(user: User) -> int | None:
    departments = getattr(user, "departments", None) or []
    return departments[0].department_id if departments else None


def _first_direction_id(user: User) -> int | None:
    directions = getattr(user, "directions", None) or []
    return directions[0].direction_id if directions else None


def _project_event_seed(project: Project, user: User) -> dict:
    data = project.form_data or {}
    return {
        "title": _clean_project_value(data.get("title")) or project.title,
        "description": (
            _clean_project_value(data.get("announcement"))
            or _clean_project_value(data.get("idea"))
            or project.short_description
        ),
        "event_date": _parse_project_date(project),
        "event_time": _parse_project_time(project),
        "location": _clean_project_value(data.get("venue_request")),
        "format": _clean_project_value(data.get("format")) or project.format,
        "department_id": project.department_id or _first_department_id(user),
        "direction_id": project.direction_id or _first_direction_id(user),
    }


async def _existing_event(session: AsyncSession, project_id: int) -> Event | None:
    marker = f"[ERA_PROJECT_ID:{project_id}]"
    return await session.scalar(
        select(Event).where(
            (Event.project_id == project_id) | (Event.additional_info.contains(marker))
        )
    )


async def _continue_project_event(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("event_date"):
        await state.set_state(ProjectEventStates.date)
        await message.answer("Укажите дату мероприятия в формате ДД.ММ.ГГГГ.")
        return
    if not data.get("event_time"):
        await state.set_state(ProjectEventStates.time)
        await message.answer("Укажите время мероприятия в формате ЧЧ:ММ.")
        return
    if not data.get("location"):
        await state.set_state(ProjectEventStates.location)
        await message.answer("Укажите место или формат площадки.")
        return
    if not data.get("format"):
        await state.set_state(ProjectEventStates.format)
        await message.answer("Укажите формат мероприятия: игра, встреча, мастер-класс, квест и т.д.")
        return
    if "participant_limit" not in data:
        await state.set_state(ProjectEventStates.participant_limit)
        await message.answer("Укажите лимит участников числом. Если лимита нет, отправьте 0.")
        return
    if "points_for_visit" not in data:
        await state.set_state(ProjectEventStates.points)
        await message.answer("Сколько баллов предложить за участие? Финально их сможет утвердить админ.")
        return


async def _create_event_from_state(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    data = await state.get_data()
    project = await _load_owned_project(session, int(data["project_id"]), user)
    if not project or project.status not in {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}:
        await state.clear()
        await message.answer("Оформить мероприятие можно только после одобрения проекта.")
        return
    existing = await _existing_event(session, project.id)
    if existing:
        await state.clear()
        await message.answer(f"Мероприятие уже создано: «{existing.title}»")
        return

    marker = f"[ERA_PROJECT_ID:{project.id}]"
    event = Event(
        title=data["title"],
        description=data["description"],
        event_date=date.fromisoformat(data["event_date"]),
        event_time=time.fromisoformat(data["event_time"]),
        location=data["location"],
        department_id=data.get("department_id"),
        direction_id=data.get("direction_id"),
        project_id=project.id,
        format=data["format"],
        responsible_id=user.id,
        participant_limit=data.get("participant_limit"),
        points_for_visit=data.get("points_for_visit", 0),
        selfie_required=False,
        additional_info=f"Создано из проекта #{project.id}\n{marker}",
        status=EventStatus.PENDING_APPROVAL,
        created_by=user.id,
    )
    session.add(event)
    project.status = ProjectStatus.IN_PROGRESS
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="project.event_created",
        entity_type="event",
        entity_id=event.id,
    )
    await state.clear()
    await message.answer(
        f"Мероприятие «{event.title}» создано из проекта и отправлено на проверку администратору."
    )
    await notify_admins(
        bot,
        settings,
        f"📅 Мероприятие из проекта #{project.id}\n\n"
        f"#{event.id} {event.title}\n"
        f"Автор: {user.first_name} {user.last_name or ''}\n"
        f"Дата: {event.event_date:%d.%m.%Y} {event.event_time:%H:%M}\n"
        f"Место: {event.location}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Открыть мероприятия", callback_data="admin:events")]
            ]
        ),
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
    project = await _load_owned_project(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project or project.status not in {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}:
        await call.message.answer("Оформить мероприятие можно после одобрения проекта.")
        return
    existing = await _existing_event(session, project.id)
    if existing:
        await call.message.answer(f"Мероприятие уже создано: «{existing.title}»")
        return
    seed = _project_event_seed(project, user)
    await state.clear()
    await state.update_data(
        project_id=project.id,
        title=seed["title"],
        description=seed["description"],
        event_date=seed["event_date"].isoformat() if seed["event_date"] else None,
        event_time=seed["event_time"].isoformat() if seed["event_time"] else None,
        location=seed["location"],
        format=seed["format"],
        department_id=seed["department_id"],
        direction_id=seed["direction_id"],
    )
    await call.message.answer(
        f"📅 Оформляем мероприятие по проекту\n\n{project.title}\n\n"
        "Часть данных возьмём из проекта. Остальное уточним сейчас."
    )
    await _continue_project_event(call.message, state)


@router.message(ProjectEventStates.date)
async def project_event_date(message: Message, state: FSMContext) -> None:
    value = parse_date(message.text or "")
    if value is None:
        await message.answer("Проверьте дату. Формат: ДД.ММ.ГГГГ.")
        return
    await state.update_data(event_date=value.isoformat())
    await _continue_project_event(message, state)


@router.message(ProjectEventStates.time)
async def project_event_time(message: Message, state: FSMContext) -> None:
    value = parse_time(message.text or "")
    if value is None:
        await message.answer("Проверьте время. Формат: ЧЧ:ММ.")
        return
    await state.update_data(event_time=value.isoformat())
    await _continue_project_event(message, state)


@router.message(ProjectEventStates.location)
async def project_event_location(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(location=value)
    await _continue_project_event(message, state)


@router.message(ProjectEventStates.format)
async def project_event_format(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 100)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(format=value)
    await _continue_project_event(message, state)


@router.message(ProjectEventStates.participant_limit)
async def project_event_limit(message: Message, state: FSMContext) -> None:
    try:
        value = int(message.text or "")
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("Укажите целое число от 0.")
        return
    await state.update_data(participant_limit=value or None)
    await _continue_project_event(message, state)


@router.message(ProjectEventStates.points)
async def project_event_points(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    try:
        value = int(message.text or "")
        if not 0 <= value <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Укажите число от 0 до 1000.")
        return
    await state.update_data(points_for_visit=value)
    await _create_event_from_state(message, state, session, user, bot, settings)
