from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.services.audit_service import audit
from app.services.authorization_service import can_manage_events
from app.services.notification_service import broadcast_detailed, safe_send
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus
from app.utils.deep_links import miniapp_event_url

router = APIRouter(prefix="/admin/events", tags=["admin-event-create"])


async def require_event_manager(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not can_manage_events(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="event_reviewer_access_required")
    return user


# ---------------------------------------------------------------------------
# Backward-compatible one-shot creator. Existing clients keep working while
# the Mini App uses the resumable wizard endpoints below.
# ---------------------------------------------------------------------------


class AdminEventCreateIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10, max_length=5000)
    event_date: date
    event_time: time
    location: str = Field(min_length=2, max_length=255)
    format: str = Field(min_length=2, max_length=100)
    participant_limit: int | None = Field(default=None, ge=1, le=5000)
    points_for_visit: int = Field(default=5, ge=0, le=200)
    needs_volunteers: bool = False
    additional_info: str | None = Field(default=None, max_length=5000)
    publish: bool = False


class AdminEventCreateOut(BaseModel):
    id: int
    title: str
    status: str
    event_date: str
    event_time: str
    location: str


@router.post("/create", response_model=AdminEventCreateOut)
async def create_event_from_admin(
    payload: AdminEventCreateIn,
    admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> AdminEventCreateOut:
    status = EventStatus.REGISTRATION_OPEN if payload.publish else EventStatus.DRAFT
    event = Event(
        title=payload.title.strip(),
        description=payload.description.strip(),
        event_date=payload.event_date,
        event_time=payload.event_time,
        location=payload.location.strip(),
        format=payload.format.strip(),
        participant_limit=payload.participant_limit,
        points_for_visit=payload.points_for_visit,
        needs_volunteers=payload.needs_volunteers,
        additional_info=payload.additional_info.strip() if payload.additional_info else None,
        status=status,
        created_by=admin.id,
        approved_by=admin.id if payload.publish else None,
    )
    session.add(event)
    await session.flush()
    session.add(
        EventExperience(
            event_id=event.id,
            short_description=payload.description.strip(),
            full_description=payload.description.strip(),
            wizard_step=10 if payload.publish else 1,
            is_complete=payload.publish,
        )
    )
    await audit(
        session,
        actor_id=admin.id,
        action="event.created_from_admin",
        entity_type="event",
        entity_id=event.id,
        new_value={"status": str(status), "published": payload.publish},
    )
    return AdminEventCreateOut(
        id=event.id,
        title=event.title,
        status=event.status,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.isoformat(timespec="minutes"),
        location=event.location,
    )


# ---------------------------------------------------------------------------
# Resumable event wizard.
# ---------------------------------------------------------------------------


class EventDraftPatch(BaseModel):
    wizard_step: int | None = Field(default=None, ge=1, le=10)
    title: str | None = Field(default=None, max_length=255)
    short_description: str | None = Field(default=None, max_length=1000)
    full_description: str | None = Field(default=None, max_length=10000)
    project_id: int | None = None
    category: str | None = Field(default=None, max_length=100)

    event_date: date | None = None
    event_time: time | None = None
    end_time: time | None = None
    location: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    attendance_mode: Literal["offline", "online", "hybrid"] | None = None

    registration_required: bool | None = None
    participant_limit: int | None = Field(default=None, ge=1, le=5000)
    registration_close_at: datetime | None = None
    waitlist_enabled: bool | None = None
    registration_audience: str | None = Field(default=None, max_length=64)

    chat_url: str | None = Field(default=None, max_length=500)
    organizer: str | None = Field(default=None, max_length=255)
    participant_value: str | None = Field(default=None, max_length=5000)
    contact: str | None = Field(default=None, max_length=255)

    program: list[dict[str, Any]] | None = None
    participant_tasks: list[dict[str, Any]] | None = None
    points_for_visit: int | None = Field(default=None, ge=0, le=200)
    reminders: list[int] | None = None
    broadcast_enabled: bool | None = None
    broadcast_targets: list[str] | None = None


class EventDraftOut(BaseModel):
    id: int
    status: str
    wizard_step: int
    is_complete: bool
    title: str
    short_description: str
    full_description: str
    project_id: int | None
    category: str | None
    event_date: str
    event_time: str
    end_time: str | None
    location: str
    address: str | None
    attendance_mode: str
    has_poster: bool
    registration_required: bool
    participant_limit: int | None
    registration_close_at: str | None
    waitlist_enabled: bool
    registration_audience: str
    chat_url: str | None
    organizer: str | None
    participant_value: str | None
    contact: str | None
    program: list[dict[str, Any]]
    participant_tasks: list[dict[str, Any]]
    points_for_visit: int
    reminders: list[int]
    broadcast_enabled: bool
    broadcast_targets: list[str]
    broadcast_estimate: int


async def _experience(session: AsyncSession, event: Event) -> EventExperience:
    item = await session.get(EventExperience, event.id)
    if item is None:
        item = EventExperience(event_id=event.id)
        session.add(item)
        await session.flush()
    return item


async def _broadcast_estimate(session: AsyncSession, experience: EventExperience) -> int:
    if not experience.broadcast_enabled:
        return 0
    targets = set(experience.broadcast_targets or [])
    if not targets.intersection({"bot", "all", "bot_and_chat"}):
        return 0
    return int(
        await session.scalar(
            select(func.count(User.id)).where(
                User.application_status == ApplicationStatus.APPROVED,
                User.is_blocked.is_(False),
                User.is_archived.is_(False),
            )
        )
        or 0
    )


async def _draft_out(session: AsyncSession, event: Event, experience: EventExperience) -> EventDraftOut:
    return EventDraftOut(
        id=event.id,
        status=event.status,
        wizard_step=experience.wizard_step,
        is_complete=experience.is_complete,
        title=event.title,
        short_description=experience.short_description or event.description or "",
        full_description=experience.full_description or event.description or "",
        project_id=event.project_id,
        category=experience.category,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.isoformat(timespec="minutes"),
        end_time=experience.end_time.isoformat(timespec="minutes") if experience.end_time else None,
        location=event.location,
        address=experience.address,
        attendance_mode=experience.attendance_mode,
        has_poster=bool(experience.poster_bytes),
        registration_required=experience.registration_required,
        participant_limit=event.participant_limit,
        registration_close_at=(experience.registration_close_at.isoformat() if experience.registration_close_at else None),
        waitlist_enabled=experience.waitlist_enabled,
        registration_audience=experience.registration_audience,
        chat_url=experience.chat_url,
        organizer=experience.organizer,
        participant_value=experience.participant_value,
        contact=experience.contact,
        program=list(experience.program or []),
        participant_tasks=list(experience.participant_tasks or []),
        points_for_visit=event.points_for_visit,
        reminders=list(experience.reminders or []),
        broadcast_enabled=experience.broadcast_enabled,
        broadcast_targets=list(experience.broadcast_targets or []),
        broadcast_estimate=await _broadcast_estimate(session, experience),
    )


async def _managed_event(session: AsyncSession, event_id: int) -> Event:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    return event


@router.post("/drafts", response_model=EventDraftOut)
async def create_event_draft(
    admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> EventDraftOut:
    today = date.today()
    event = Event(
        title="Новое мероприятие",
        description="",
        event_date=today,
        event_time=time(hour=12),
        location="",
        format="Событие",
        participant_limit=None,
        points_for_visit=0,
        needs_volunteers=False,
        status=EventStatus.DRAFT,
        created_by=admin.id,
    )
    session.add(event)
    await session.flush()
    experience = EventExperience(event_id=event.id, wizard_step=1, is_complete=False)
    session.add(experience)
    await session.flush()
    await audit(
        session,
        actor_id=admin.id,
        action="event.draft_created",
        entity_type="event",
        entity_id=event.id,
    )
    return await _draft_out(session, event, experience)


@router.get("/drafts", response_model=list[EventDraftOut])
async def list_event_drafts(
    admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> list[EventDraftOut]:
    events = list(
        (
            await session.scalars(
                select(Event)
                .where(Event.status == EventStatus.DRAFT, Event.created_by == admin.id)
                .order_by(Event.updated_at.desc())
            )
        ).all()
    )
    result: list[EventDraftOut] = []
    for event in events:
        result.append(await _draft_out(session, event, await _experience(session, event)))
    return result


@router.get("/{event_id}/draft", response_model=EventDraftOut)
async def read_event_draft(
    event_id: int,
    _admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> EventDraftOut:
    event = await _managed_event(session, event_id)
    return await _draft_out(session, event, await _experience(session, event))


async def _notify_changed_event(
    bot: Bot | None,
    settings: Settings,
    session: AsyncSession,
    event: Event,
    changes: list[str],
) -> None:
    if bot is None or not changes:
        return
    rows = await session.execute(
        select(User.telegram_id)
        .join(EventRegistration, EventRegistration.user_id == User.id)
        .where(
            EventRegistration.event_id == event.id,
            EventRegistration.status.in_(
                [RegistrationStatus.REGISTERED, RegistrationStatus.WILL_COME, RegistrationStatus.WAITLIST]
            ),
        )
    )
    recipients = [int(value) for value in rows.scalars().all() if value]
    if not recipients:
        return
    url = miniapp_event_url(settings.effective_miniapp_url, event.id)
    markup = (
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Открыть мероприятие", web_app=WebAppInfo(url=url))]]
        )
        if url
        else None
    )
    text = "⚡ Изменились детали мероприятия\n\n" + event.title + "\n\n" + "\n".join(f"• {item}" for item in changes)
    await broadcast_detailed(bot, recipients, text, reply_markup=markup)


@router.patch("/{event_id}/draft", response_model=EventDraftOut)
async def save_event_draft_step(
    event_id: int,
    payload: EventDraftPatch,
    _admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> EventDraftOut:
    event = await _managed_event(session, event_id)
    experience = await _experience(session, event)
    was_public = event.status != EventStatus.DRAFT
    changes: list[str] = []

    if payload.title is not None:
        event.title = payload.title.strip() or event.title
    if payload.short_description is not None:
        experience.short_description = payload.short_description.strip()
    if payload.full_description is not None:
        experience.full_description = payload.full_description.strip()
        event.description = payload.full_description.strip()
    if payload.project_id is not None:
        event.project_id = payload.project_id
    if payload.category is not None:
        experience.category = payload.category.strip() or None

    if payload.event_date is not None and payload.event_date != event.event_date:
        event.event_date = payload.event_date
        changes.append(f"Новая дата: {event.event_date.strftime('%d.%m.%Y')}")
    if payload.event_time is not None and payload.event_time != event.event_time:
        event.event_time = payload.event_time
        changes.append(f"Новое время: {event.event_time.strftime('%H:%M')}")
    if payload.end_time is not None:
        experience.end_time = payload.end_time
    if payload.location is not None and payload.location.strip() != event.location:
        event.location = payload.location.strip()
        changes.append(f"Новое место: {event.location}")
    if payload.address is not None:
        experience.address = payload.address.strip() or None
    if payload.attendance_mode is not None:
        experience.attendance_mode = payload.attendance_mode
        event.format = {"offline": "Офлайн", "online": "Онлайн", "hybrid": "Гибрид"}[payload.attendance_mode]

    if payload.registration_required is not None:
        experience.registration_required = payload.registration_required
    if "participant_limit" in payload.model_fields_set:
        event.participant_limit = payload.participant_limit
    if "registration_close_at" in payload.model_fields_set:
        experience.registration_close_at = payload.registration_close_at
    if payload.waitlist_enabled is not None:
        experience.waitlist_enabled = payload.waitlist_enabled
    if payload.registration_audience is not None:
        experience.registration_audience = payload.registration_audience

    if "chat_url" in payload.model_fields_set:
        experience.chat_url = payload.chat_url.strip() if payload.chat_url else None
    if "organizer" in payload.model_fields_set:
        experience.organizer = payload.organizer.strip() if payload.organizer else None
    if "participant_value" in payload.model_fields_set:
        experience.participant_value = payload.participant_value.strip() if payload.participant_value else None
    if "contact" in payload.model_fields_set:
        experience.contact = payload.contact.strip() if payload.contact else None

    if payload.program is not None:
        experience.program = payload.program
    if payload.participant_tasks is not None:
        experience.participant_tasks = payload.participant_tasks
    if payload.points_for_visit is not None:
        event.points_for_visit = payload.points_for_visit
    if payload.reminders is not None:
        experience.reminders = sorted({max(5, int(value)) for value in payload.reminders})
    if payload.broadcast_enabled is not None:
        experience.broadcast_enabled = payload.broadcast_enabled
    if payload.broadcast_targets is not None:
        experience.broadcast_targets = list(dict.fromkeys(payload.broadcast_targets))
    if payload.wizard_step is not None:
        experience.wizard_step = payload.wizard_step

    await session.flush()
    if was_public and changes:
        await _notify_changed_event(bot, settings, session, event, changes)
    return await _draft_out(session, event, experience)


@router.post("/{event_id}/poster", response_model=EventDraftOut)
async def upload_event_poster(
    event_id: int,
    file: UploadFile = File(...),
    _admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> EventDraftOut:
    event = await _managed_event(session, event_id)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="poster_must_be_image")
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="poster_too_large")
    experience = await _experience(session, event)
    experience.poster_bytes = content
    experience.poster_content_type = file.content_type
    return await _draft_out(session, event, experience)


@router.post("/{event_id}/poster/remove", response_model=EventDraftOut)
async def remove_event_poster(
    event_id: int,
    _admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
) -> EventDraftOut:
    event = await _managed_event(session, event_id)
    experience = await _experience(session, event)
    experience.poster_bytes = None
    experience.poster_content_type = None
    return await _draft_out(session, event, experience)


def _validate_publish(event: Event, experience: EventExperience) -> list[str]:
    missing: list[str] = []
    if not event.title.strip() or event.title == "Новое мероприятие":
        missing.append("title")
    if not (experience.full_description or event.description).strip():
        missing.append("full_description")
    if not event.location.strip():
        missing.append("location")
    if experience.registration_required and event.participant_limit is not None and event.participant_limit < 1:
        missing.append("participant_limit")
    return missing


async def _publish_broadcast(
    bot: Bot | None,
    settings: Settings,
    session: AsyncSession,
    event: Event,
    experience: EventExperience,
) -> None:
    if bot is None or not experience.broadcast_enabled:
        return
    targets = set(experience.broadcast_targets or [])
    url = miniapp_event_url(settings.effective_miniapp_url, event.id)
    markup = (
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Открыть мероприятие", web_app=WebAppInfo(url=url))]]
        )
        if url
        else None
    )
    text = (
        f"🔥 {event.title}\n\n"
        f"{experience.short_description or event.description}\n\n"
        f"📅 {event.event_date.strftime('%d.%m.%Y')} · {event.event_time.strftime('%H:%M')}\n"
        f"📍 {event.location}"
    )
    if targets.intersection({"bot", "all", "bot_and_chat"}):
        recipient_rows = await session.scalars(
            select(User.telegram_id).where(
                User.application_status == ApplicationStatus.APPROVED,
                User.is_blocked.is_(False),
                User.is_archived.is_(False),
            )
        )
        await broadcast_detailed(bot, [int(value) for value in recipient_rows.all() if value], text, reply_markup=markup)
    if targets.intersection({"general", "all", "bot_and_chat"}) and settings.general_chat_id:
        await safe_send(bot, int(settings.general_chat_id), text, reply_markup=markup)


@router.post("/{event_id}/publish", response_model=EventDraftOut)
async def publish_event(
    event_id: int,
    admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> EventDraftOut:
    event = await _managed_event(session, event_id)
    experience = await _experience(session, event)
    missing = _validate_publish(event, experience)
    if missing:
        raise HTTPException(status_code=422, detail="missing:" + ",".join(missing))
    event.status = EventStatus.REGISTRATION_OPEN if experience.registration_required else EventStatus.PUBLISHED
    event.approved_by = admin.id
    experience.wizard_step = 10
    experience.is_complete = True
    await session.flush()
    await audit(
        session,
        actor_id=admin.id,
        action="event.published_from_wizard",
        entity_type="event",
        entity_id=event.id,
        new_value={"status": str(event.status)},
    )
    await _publish_broadcast(bot, settings, session, event, experience)
    return await _draft_out(session, event, experience)


@router.post("/{event_id}/cancel", response_model=EventDraftOut)
async def cancel_event(
    event_id: int,
    admin: User = Depends(require_event_manager),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> EventDraftOut:
    event = await _managed_event(session, event_id)
    experience = await _experience(session, event)
    event.status = EventStatus.CANCELLED
    await session.flush()
    await _notify_changed_event(bot, settings, session, event, ["Мероприятие отменено"])
    await audit(
        session,
        actor_id=admin.id,
        action="event.cancelled",
        entity_type="event",
        entity_id=event.id,
    )
    return await _draft_out(session, event, experience)
