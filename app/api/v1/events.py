from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.services import event_activity_service
from app.services.activity_service import EventScope, list_events
from app.services.event_registration_service import mark_not_coming
from app.services.event_service import (
    available_places,
    promote_waitlist,
    register_for_event,
    registered_count,
)
from app.services.notification_service import safe_send
from app.utils.constants import EventStatus, RegistrationStatus
from app.utils.deep_links import activity_submit_deep_link, miniapp_event_url

router = APIRouter(prefix="/events", tags=["events"])


class EventOut(BaseModel):
    id: int
    title: str
    description: str
    short_description: str | None = None
    full_description: str | None = None
    event_date: str
    event_time: str
    end_time: str | None = None
    location: str
    address: str | None = None
    format: str
    attendance_mode: str = "offline"
    category: str | None = None
    organizer: str | None = None
    participant_value: str | None = None
    contact: str | None = None
    chat_url: str | None = None
    points_for_visit: int
    project_id: int | None
    status: str
    display_status: str
    participant_limit: int | None
    registered_count: int
    available_places: str
    remaining_count: int | None
    registration_status: str | None
    waitlist_enabled: bool = False
    registration_required: bool = True
    registration_close_at: str | None = None
    can_register: bool = False
    program: list[dict[str, Any]]
    participant_tasks: list[dict[str, Any]]
    poster_url: str | None = None


def _registration_is_closed(experience: EventExperience | None) -> bool:
    if experience is None or experience.registration_close_at is None:
        return False
    deadline = experience.registration_close_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline <= datetime.now(timezone.utc)


def _display_status(
    event: Event,
    registration: EventRegistration | None,
    remaining: int | None,
) -> str:
    if registration is not None:
        if registration.status == RegistrationStatus.WAITLIST:
            return "Вы в листе ожидания"
        if registration.status in {
            RegistrationStatus.REGISTERED,
            RegistrationStatus.WILL_COME,
            RegistrationStatus.ATTENDED,
        }:
            return "Вы зарегистрированы"
    if event.status in {EventStatus.COMPLETED, EventStatus.REPORT_SUBMITTED}:
        return "Завершено"
    if event.status == EventStatus.CANCELLED:
        return "Отменено"
    if event.status == EventStatus.REGISTRATION_CLOSED:
        return "Регистрация закрыта"
    if remaining is not None and remaining <= 3:
        return "Мест почти нет" if remaining > 0 else "Мест нет"
    if event.status in {EventStatus.APPROVED, EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN}:
        return "Регистрация открыта"
    return "Скоро"


async def _to_event_out(
    session: AsyncSession, event: Event, registration: EventRegistration | None
) -> EventOut:
    experience = await session.get(EventExperience, event.id)
    places = await available_places(session, event)
    count = await registered_count(session, event.id)
    remaining = None if event.participant_limit is None else max(0, event.participant_limit - count)

    organizer = experience.organizer if experience else None
    if not organizer:
        creator = await session.get(User, event.created_by)
        if creator is not None:
            organizer = f"{creator.first_name} {creator.last_name or ''}".strip()

    registration_required = experience.registration_required if experience else True
    waitlist_enabled = experience.waitlist_enabled if experience else False
    registration_closed = _registration_is_closed(experience)
    active_registration = bool(
        registration
        and registration.status
        in {
            RegistrationStatus.REGISTERED,
            RegistrationStatus.WILL_COME,
            RegistrationStatus.WAITLIST,
            RegistrationStatus.ATTENDED,
        }
    )
    can_register = (
        registration_required
        and not active_registration
        and not registration_closed
        and event.status in {EventStatus.APPROVED, EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN}
        and (remaining is None or remaining > 0 or waitlist_enabled)
    )

    return EventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        short_description=(experience.short_description if experience else None) or event.description,
        full_description=(experience.full_description if experience else None) or event.description,
        event_date=event.event_date.isoformat(),
        event_time=event.event_time.isoformat(timespec="minutes"),
        end_time=(experience.end_time.isoformat(timespec="minutes") if experience and experience.end_time else None),
        location=event.location,
        address=experience.address if experience else None,
        format=event.format,
        attendance_mode=experience.attendance_mode if experience else "offline",
        category=experience.category if experience else None,
        organizer=organizer,
        participant_value=experience.participant_value if experience else None,
        contact=experience.contact if experience else None,
        chat_url=experience.chat_url if experience else None,
        points_for_visit=event.points_for_visit,
        project_id=event.project_id,
        status=event.status,
        display_status=_display_status(event, registration, remaining),
        participant_limit=event.participant_limit,
        registered_count=count,
        available_places=places,
        remaining_count=remaining,
        registration_status=registration.status if registration else None,
        waitlist_enabled=waitlist_enabled,
        registration_required=registration_required,
        registration_close_at=(
            experience.registration_close_at.isoformat()
            if experience and experience.registration_close_at
            else None
        ),
        can_register=can_register,
        program=list(experience.program or []) if experience else [],
        participant_tasks=list(experience.participant_tasks or []) if experience else [],
        poster_url=(f"/api/v1/events/{event.id}/poster" if experience and experience.poster_bytes else None),
    )


async def _get_registration(
    session: AsyncSession, event_id: int, user_id: int
) -> EventRegistration | None:
    return await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id, EventRegistration.user_id == user_id
        )
    )


def _event_keyboard(settings: Settings, event: Event, experience: EventExperience | None) -> InlineKeyboardMarkup | None:
    url = miniapp_event_url(settings.effective_miniapp_url, event.id)
    rows: list[list[InlineKeyboardButton]] = []
    if url:
        rows.append([InlineKeyboardButton(text="Открыть мероприятие", web_app=WebAppInfo(url=url))])
    if experience and experience.chat_url:
        rows.append([InlineKeyboardButton(text="Открыть чат", url=experience.chat_url)])
    if url:
        rows.append([InlineKeyboardButton(text="Отказаться от участия", web_app=WebAppInfo(url=url))])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def _send_registration_confirmation(
    bot: Bot | None,
    settings: Settings,
    user: User,
    event: Event,
    experience: EventExperience | None,
    registration: EventRegistration,
) -> None:
    if bot is None:
        return
    if registration.status == RegistrationStatus.WAITLIST:
        text = (
            "🔥 Вы в листе ожидания\n\n"
            f"{event.title}\n\n"
            f"📅 {event.event_date.strftime('%d.%m.%Y')}\n"
            f"🕐 {event.event_time.strftime('%H:%M')}\n"
            f"📍 {event.location}\n\n"
            "Сейчас свободных мест нет. Если место освободится, мы автоматически переведём вас в список участников и сообщим об этом."
        )
    else:
        text = (
            "🔥 Вы зарегистрированы\n\n"
            f"{event.title}\n\n"
            f"📅 {event.event_date.strftime('%d.%m.%Y')}\n"
            f"🕐 {event.event_time.strftime('%H:%M')}\n"
            f"📍 {event.location}\n\n"
            "Мы напомним вам о встрече заранее.\n\n"
            "Если планы изменятся — пожалуйста, отмените участие. Так ваше место сможет занять другой участник."
        )
    await safe_send(
        bot,
        user.telegram_id,
        text,
        reply_markup=_event_keyboard(settings, event, experience),
    )


@router.get("", response_model=list[EventOut])
async def read_events(
    scope: EventScope = Query("all"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[EventOut]:
    rows = await list_events(session, user, scope)
    return [await _to_event_out(session, event, registration) for event, registration in rows]


@router.get("/{event_id}/poster")
async def read_event_poster(
    event_id: int,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    experience = await session.get(EventExperience, event_id)
    if experience is None or not experience.poster_bytes:
        raise HTTPException(status_code=404, detail="event_poster_not_found")
    return Response(
        content=experience.poster_bytes,
        media_type=experience.poster_content_type or "image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/{event_id}", response_model=EventOut)
async def read_event(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EventOut:
    event = await session.get(Event, event_id)
    if event is None or event.status == EventStatus.DRAFT:
        raise HTTPException(status_code=404, detail="event_not_found")
    registration = await _get_registration(session, event_id, user.id)
    return await _to_event_out(session, event, registration)


@router.post("/{event_id}/register", response_model=EventOut)
async def register_event(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> EventOut:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    experience = await session.get(EventExperience, event_id)
    if _registration_is_closed(experience):
        raise HTTPException(status_code=409, detail="closed")
    if experience is not None and not experience.registration_required:
        raise HTTPException(status_code=409, detail="registration_not_required")
    registration, error = await register_for_event(
        session,
        event,
        user.id,
        waitlist_enabled=bool(experience and experience.waitlist_enabled),
    )
    if error:
        raise HTTPException(status_code=409, detail=error)
    assert registration is not None
    await _send_registration_confirmation(bot, settings, user, event, experience, registration)
    return await _to_event_out(session, event, registration)


@router.post("/{event_id}/cancel", response_model=EventOut)
async def cancel_event_registration(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> EventOut:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    registration = await _get_registration(session, event_id, user.id)
    if registration is None:
        raise HTTPException(status_code=404, detail="registration_not_found")
    was_waiting = registration.status == RegistrationStatus.WAITLIST
    if was_waiting:
        registration.status = RegistrationStatus.CANCELLED
    elif not mark_not_coming(registration, event):
        raise HTTPException(status_code=409, detail="cannot_change_plans")

    promoted = None if was_waiting else await promote_waitlist(session, event)
    if promoted is not None and bot is not None:
        promoted_user = await session.get(User, promoted.user_id)
        experience = await session.get(EventExperience, event.id)
        if promoted_user is not None:
            await safe_send(
                bot,
                promoted_user.telegram_id,
                "🔥 Для вас освободилось место\n\n"
                f"Вы теперь зарегистрированы на «{event.title}».\n\n"
                f"📅 {event.event_date.strftime('%d.%m.%Y')} · {event.event_time.strftime('%H:%M')}\n"
                f"📍 {event.location}",
                reply_markup=_event_keyboard(settings, event, experience),
            )
    return await _to_event_out(session, event, registration)


class EventActivityOut(BaseModel):
    id: int
    title: str
    description: str
    submission_type: str
    points: int
    my_status: str | None
    submit_deep_link: str | None


@router.get("/{event_id}/activities", response_model=list[EventActivityOut])
async def read_event_activities(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[EventActivityOut]:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    activities = await event_activity_service.list_activities_for_participant(session, event, user)
    if activities is None:
        raise HTTPException(status_code=409, detail="not_registered")
    result: list[EventActivityOut] = []
    for activity in activities:
        submission = await event_activity_service.get_submission(session, activity.id, user.id)
        can_submit = submission is None or submission.status not in {"approved", "pending"}
        result.append(
            EventActivityOut(
                id=activity.id,
                title=activity.title,
                description=activity.description,
                submission_type=activity.submission_type,
                points=activity.points,
                my_status=submission.status if submission else None,
                submit_deep_link=(
                    activity_submit_deep_link(settings.bot_username, activity.id)
                    if can_submit and settings.bot_username
                    else None
                ),
            )
        )
    return result
