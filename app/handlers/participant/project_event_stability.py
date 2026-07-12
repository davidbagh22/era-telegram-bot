from __future__ import annotations

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, Project, User
from app.services.notification_service import notify_admins
from app.utils import texts
from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus

router = Router(name="participant_project_event_stability")


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


def _project_date(project: Project, data: dict) -> object | None:
    if project.proposed_date:
        return project.proposed_date
    raw = data.get("proposed_date")
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def _project_time(project: Project, data: dict) -> object | None:
    if project.proposed_time:
        return project.proposed_time
    raw = data.get("proposed_time")
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%H:%M").time()
    except ValueError:
        return None


@router.callback_query(F.data.startswith("project:event:"))
async def project_event_stable(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    project = await _load_owned(session, int(call.data.rsplit(":", 1)[-1]), user)
    if not project or project.status not in {ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS}:
        await call.message.answer("Оформить мероприятие можно после одобрения проекта")
        return

    marker = f"[ERA_PROJECT_ID:{project.id}]"
    existing = await session.scalar(select(Event).where(Event.project_id == project.id))
    if existing is None:
        existing = await session.scalar(select(Event).where(Event.additional_info.contains(marker)))
    if existing:
        await call.message.answer(f"Мероприятие уже создано: «{existing.title}»")
        return

    data = dict(project.form_data or {})
    event_date = _project_date(project, data)
    event_time = _project_time(project, data)
    if event_date is None or event_time is None:
        await call.message.answer(
            "В проекте нет корректной даты или времени\n\n"
            "Откройте проект, исправьте дату в формате ДД.ММ.ГГГГ и время в формате ЧЧ:ММ, затем отправьте его на проверку снова"
        )
        return

    event = Event(
        title=data.get("title") or project.title,
        description=data.get("announcement") or data.get("idea") or project.short_description,
        event_date=event_date,
        event_time=event_time,
        location=data.get("venue_request") or "Требуется согласование площадки",
        format=data.get("format") or "мероприятие",
        responsible_id=user.id,
        participant_limit=None,
        points_for_visit=5,
        selfie_required=False,
        project_id=project.id,
        additional_info=marker,
        status=EventStatus.PENDING_APPROVAL,
        created_by=user.id,
    )
    session.add(event)
    project.status = ProjectStatus.IN_PROGRESS
    await session.flush()
    await call.message.answer(
        f"Мероприятие «{event.title}» создано из проекта и отправлено на утверждение"
    )
    await notify_admins(
        bot,
        settings,
        f"📅 Мероприятие из проекта #{project.id}\n\n"
        f"#{event.id} {event.title}\n"
        f"Дата: {event.event_date:%d.%m.%Y} {event.event_time:%H:%M}\n"
        f"Площадка: {event.location}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Открыть мероприятия", callback_data="admin:events")]
            ]
        ),
    )
