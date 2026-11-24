from __future__ import annotations

import hashlib
import logging

from typing import Any

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.services import anniversary_registration_service as anniversary, event_activity_service
from app.services.activity_service import EventScope, list_events
from app.services.event_registration_policy import registration_is_closed
from app.services.event_registration_notice_service import (
    RegistrationNoticeKind,
    deliver_registration_notice,
    enqueue_registration_notice,
)
from app.services.event_poster_security import normalized_event_poster_mime
from app.services.event_service import (
    available_places,
    leave_event_registration,
    register_for_event,
    registered_count,
)
from app.services.notification_service import safe_send_once
from app.services.event_calendar_service import build_event_calendar
from app.services.event_service import PUBLIC_EVENT_STATUSES
from app.utils.constants import EventStatus, RegistrationStatus
from app.utils.deep_links import activity_submit_deep_link

router = APIRouter(prefix="/events", tags=["events"])
logger = logging.getLogger(__name__)


class AnniversaryRegistrationIn(BaseModel):
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    organization: str | None = Field(default=None, max_length=160)


class EventSignup(BaseModel):
    full_name: str = Field(min_length=3, max_length=255, pattern=r"^\S+(?:\s+\S+){2,}$")
    phone: str = Field(min_length=7, max_length=32, pattern=r"^\+?[0-9 ()-]+$")
    organization: str = Field(min_length=2, max_length=255)


class EventOut(BaseModel):
    signup_defaults: dict[str, str] | None = None
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
    registration_url: str | None = None
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
    registration_url: str | None = None
    can_register: bool = False
    program: list[dict[str, Any]]
    participant_tasks: list[dict[str, Any]]
    poster_url: str | None = None
    anniversary_registered: bool | None = None
    anniversary_registration_open: bool = False
    anniversary_defaults: AnniversaryRegistrationIn | None = None


def _display_status(
    event: Event,
    registration: EventRegistration | None,
    remaining: int | None,
    *,
    registration_required: bool = True,
    registration_closed: bool = False,
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
    if event.status == EventStatus.ACTIVE:
        return "Идёт сейчас"
    if event.status == EventStatus.REGISTRATION_CLOSED or (
        registration_closed and registration_required
    ):
        return "Регистрация закрыта"
    if remaining is not None and remaining <= 3:
        return "Мест почти нет" if remaining > 0 else "Мест нет"
    if event.status in {EventStatus.APPROVED, EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN}:
        return "Регистрация открыта" if registration_required else "Без регистрации"
    if event.status in {EventStatus.DRAFT, EventStatus.PENDING_APPROVAL}:
        return "Готовится"
    return "Скоро"


async def _to_event_out(
    session: AsyncSession, event: Event, registration: EventRegistration | None, user: User
) -> EventOut:
    experience = await session.get(EventExperience, event.id)
    guest_event = (
        anniversary.is_public_anniversary(event) and event.status in anniversary.DISPLAY_STATUSES
    )
    count = await anniversary.attendee_count(session, event) if guest_event else await registered_count(session, event.id)
    places = await available_places(session, event)
    if guest_event and event.participant_limit is not None:
        places = str(max(0, event.participant_limit - count))
    remaining = None if event.participant_limit is None else max(0, event.participant_limit - count)

    organizer = experience.organizer if experience else None
    external_signup = bool(
        experience and not experience.registration_required
        and (getattr(experience, "registration_url", None) or str(experience.contact or "").startswith("https://t.me/"))
    )
    # For events hosted by other organizers, the ERA admin who shared the
    # listing is not necessarily its organizer.
    if not organizer and not external_signup:
        creator = await session.get(User, event.created_by)
        if creator is not None:
            organizer = f"{creator.first_name} {creator.last_name or ''}".strip()

    registration_required = experience.registration_required if experience else True
    waitlist_enabled = experience.waitlist_enabled if experience else False
    registration_closed = registration_is_closed(experience)
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
    anniversary_registered = None
    anniversary_open = False
    anniversary_defaults = None
    display_status = _display_status(
        event,
        registration,
        remaining,
        registration_required=registration_required,
        registration_closed=registration_closed,
    )
    if display_status == "Без регистрации" and external_signup:
        display_status = "Запись по ссылке организаторов"
    if guest_event:
        waitlisted = registration is not None and registration.status == RegistrationStatus.WAITLIST
        anniversary_registered = (
            (registration is not None and registration.status in anniversary.ACTIVE_REGISTRATION_STATUSES)
            or bool(await anniversary.get_registration(session, user.telegram_id))
        )
        anniversary_open = (
            not waitlisted and anniversary.event_registration_open(event, experience) and (remaining is None or remaining > 0)
        )
        if anniversary_open and not anniversary_registered:
            anniversary_defaults = AnniversaryRegistrationIn(**anniversary.profile_defaults(user))
        can_register = False
        if anniversary_registered:
            display_status = "Вы зарегистрированы"
        elif not waitlisted and not anniversary_open and event.status in anniversary.FEATURED_STATUSES:
            display_status = "Мест нет" if remaining == 0 else "Регистрация закрыта"

    return EventOut(
        id=event.id,
        signup_defaults={
            "full_name": f"{user.last_name or ''} {user.first_name or ''}".strip(),
            "phone": user.phone or "", "organization": user.education_work or "",
        } if experience and "project_topic" in (getattr(experience, "broadcast_targets", None) or []) else None,
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
        registration_url=getattr(experience, "registration_url", None) if experience else None,
        points_for_visit=event.points_for_visit,
        project_id=event.project_id,
        status=event.status,
        display_status=display_status,
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
        anniversary_registered=anniversary_registered,
        anniversary_registration_open=anniversary_open,
        anniversary_defaults=anniversary_defaults,
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


async def _require_participant_event(
    session: AsyncSession, event_id: int, user: User
) -> tuple[Event, EventRegistration | None]:
    """Same visibility gate as GET /events/{id}: hide drafts and unregistered
    cancelled events so status-code oracles cannot enumerate them."""
    event = await session.get(Event, event_id)
    if event is None or event.status in {EventStatus.DRAFT, EventStatus.PENDING_APPROVAL}:
        raise HTTPException(status_code=404, detail="event_not_found")
    registration = await _get_registration(session, event_id, user.id)
    if event.status == EventStatus.CANCELLED and registration is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    return event, registration


@router.get("", response_model=list[EventOut])
async def read_events(
    scope: EventScope = Query("all"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[EventOut]:
    rows = await list_events(session, user, scope)
    if scope in {"mine", "past"}:
        event = await anniversary.find_event(session)
        if (
            event is not None and event.status in anniversary.DISPLAY_STATUSES and event.access_type == "all"
            and all(item.id != event.id for item, _ in rows)
            and (scope == "mine" or anniversary.event_has_started())
            and await anniversary.get_registration(session, user.telegram_id)
        ):
            rows.append((event, None))
            rows.sort(key=lambda row: (row[0].event_date, row[0].event_time), reverse=scope == "past")
    return [await _to_event_out(session, event, registration, user) for event, registration in rows]


@router.get("/{event_id}/poster")
async def read_event_poster(
    event_id: int,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # An event awaiting moderation (or still a draft) must not leak its
    # unpublished poster through a guessed numeric event ID.
    event = await session.get(Event, event_id)
    if event is None or event.status in {EventStatus.DRAFT, EventStatus.PENDING_APPROVAL}:
        raise HTTPException(status_code=404, detail="event_poster_not_found")
    # Cancellation alone is not proof of prior publication. Keep posters for
    # registered history only — same policy as calendar.ics delivery.
    if event.status == EventStatus.CANCELLED and await _get_registration(
        session, event_id, _user.id
    ) is None:
        raise HTTPException(status_code=404, detail="event_poster_not_found")
    experience = await session.get(EventExperience, event_id)
    if experience is None or not experience.poster_bytes:
        raise HTTPException(status_code=404, detail="event_poster_not_found")
    # Poster metadata may come from legacy imports or moderator uploads.
    # Never serve HTML/SVG (including scripts) under the Mini App origin.
    # Refuse unsupported MIME types rather than reflecting untrusted values.
    poster_mime = normalized_event_poster_mime(experience.poster_content_type)
    if poster_mime is None:
        raise HTTPException(status_code=404, detail="event_poster_not_found")
    return Response(
        content=experience.poster_bytes,
        media_type=poster_mime,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


async def _calendar_payload(
    event_id: int, user: User, session: AsyncSession, settings: Settings,
) -> bytes:
    """Enforce the same event visibility and access policy for ICS delivery."""
    from app.utils.constants import ApplicationStatus
    if user.application_status != ApplicationStatus.APPROVED:
        raise HTTPException(status_code=403, detail="application_not_approved")
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    registration = await _get_registration(session, event_id, user.id)
    if event.status not in PUBLIC_EVENT_STATUSES and not (
        registration and event.status in {EventStatus.ACTIVE, EventStatus.CANCELLED, EventStatus.COMPLETED, EventStatus.REPORT_SUBMITTED}
    ):
        raise HTTPException(status_code=404, detail="event_not_found")
    experience = await session.get(EventExperience, event_id)
    return build_event_calendar(event, experience, timezone_name=settings.timezone)


@router.get("/{event_id}/calendar.ics")
async def read_event_calendar(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    payload = await _calendar_payload(event_id, user, session, settings)
    return Response(payload, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="ERA-{event_id}.ics"',
                             "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/{event_id}/calendar/send")
async def send_event_calendar_to_chat(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> dict[str, bool]:
    """Explicit iOS fallback: send private ICS document to user's bot chat."""
    from aiogram.types import BufferedInputFile

    payload = await _calendar_payload(event_id, user, session, settings)
    if bot is None:
        raise HTTPException(status_code=503, detail="bot_unavailable")
    # A Telegram timeout may happen after the document was accepted. Persist a
    # versioned claim before sending, and never replay an uncertain delivery.
    # Changed ICS bytes create a different key; unchanged retries reuse it.
    digest = hashlib.sha256(payload).hexdigest()
    key = f"event-calendar:{user.id}:{event_id}:{digest}"
    try:
        outcome = await safe_send_once(
            bot, settings, int(user.telegram_id),
            "Откройте файл и добавьте мероприятие в Календарь.",
            delivery_key=key,
            notification_type="event_calendar_file",
            document=BufferedInputFile(payload, filename=f"ERA-{event_id}.ics"),
            max_attempts=1,
        )
    except Exception as exc:
        # A durable pending claim may exist; never send again from this handler.
        raise HTTPException(status_code=502, detail="telegram_send_failed") from exc
    if outcome.sent:
        return {"sent": True}
    if outcome.status in {"pending", "uncertain", "conflict"}:
        raise HTTPException(status_code=409, detail="calendar_delivery_unconfirmed")
    raise HTTPException(status_code=502, detail="telegram_send_failed")


@router.get("/{event_id}", response_model=EventOut)
async def read_event(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EventOut:
    # A cancelled draft has no reliable publication marker. Do not expose its
    # title/location to an unrelated participant by numeric event ID.
    event, registration = await _require_participant_event(session, event_id, user)
    return await _to_event_out(session, event, registration, user)


@router.post("/{event_id}/anniversary-rsvp", response_model=EventOut)
async def register_anniversary(
    event_id: int,
    payload: AnniversaryRegistrationIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EventOut:
    event = await session.get(Event, event_id)
    if event is None or not anniversary.is_public_anniversary(event) or event.status not in anniversary.FEATURED_STATUSES:
        raise HTTPException(status_code=404, detail="event_not_found")
    try:
        already_registered = await anniversary.check_event_registration(session, event, user.telegram_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=404 if str(exc) == "event_not_found" else 409, detail=str(exc)) from exc
    if not already_registered:
        fields = anniversary.profile_defaults(user) | payload.model_dump(exclude_none=True)
        if len(fields) < 3:
            raise HTTPException(status_code=409, detail="anniversary_profile_incomplete")
        try:
            for key, value in fields.items():
                fields[key] = anniversary.clean_field(value, name=key != "organization")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="anniversary_invalid_fields") from exc
        try:
            await anniversary.register(session, user.telegram_id, fields)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="anniversary_registration_closed") from exc
    registration = await _get_registration(session, event.id, user.id)
    return await _to_event_out(session, event, registration, user)


@router.post("/{event_id}/register", response_model=EventOut)
async def register_event(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
    signup: EventSignup | None = None,
) -> EventOut:
    # Match detail/poster privacy: do not confirm CANCELLED existence via 409.
    event, _existing = await _require_participant_event(session, event_id, user)
    policy = await session.get(EventExperience, event_id)
    if policy is not None and not policy.registration_required and (getattr(policy, "registration_url", None) or str(policy.contact or "").startswith("https://t.me/")):
        raise HTTPException(status_code=409, detail="external_registration_only")
    if signup is not None:
        policy = await session.get(EventExperience, event_id)
        if policy is None or "project_topic" not in (policy.broadcast_targets or []):
            raise HTTPException(422, "Анкета не требуется для этого мероприятия")
        if not signup.organization.strip() or sum(ch.isdigit() for ch in signup.phone) < 7:
            raise HTTPException(422, "Проверьте название организации и номер телефона")
        registration, error = await register_for_event(session, event, user.id, signup.model_dump())
    else:
        registration, error = await register_for_event(session, event, user.id)
    if error:
        raise HTTPException(status_code=409, detail=error)
    assert registration is not None
    notice = None
    if bot is not None:
        notice = await enqueue_registration_notice(session, registration, user.telegram_id, RegistrationNoticeKind.MINI_APP)
    result = await _to_event_out(session, event, registration, user)
    await session.commit()
    # Registration has already been committed. A Telegram outage must not
    # tell the participant that their registration failed or cause a retry.
    if notice is not None and bot is not None:
        try:
            await deliver_registration_notice(session, notice, bot.send_message, settings)
        except Exception:
            logger.exception("Registration saved, notice delivery pending event_id=%s", event.id)
    if signup is not None and bot and registration.status == RegistrationStatus.REGISTERED:
        try:
            manager = await session.get(User, settings.era_chair_user_id or event.created_by)
            from app.services.authorization_service import can_manage_events
            if manager and can_manage_events(manager, settings, manager.telegram_id):
                await safe_send_once(bot, settings, manager.telegram_id,
                    f"Новая регистрация · {event.title}\n{event.event_date:%d.%m.%Y} · {event.event_time:%H:%M}\n"
                    f"{event.location}\n{result.chat_url or ''}\n\n{signup.full_name}\n{signup.phone}\n{signup.organization}",
                    delivery_key=f"organizer:{notice or registration.id}",
                    notification_type="event_signup", max_attempts=1)
        except Exception:
            logger.exception("Registration saved, organizer delivery pending event_id=%s", event.id)
    return result


@router.post("/{event_id}/cancel", response_model=EventOut)
async def cancel_event_registration(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> EventOut:
    # Unregistered callers must not learn that a cancelled event id exists
    # through a distinct registration_not_found response.
    _event, registration = await _require_participant_event(session, event_id, user)
    if registration is None:
        raise HTTPException(status_code=404, detail="registration_not_found")
    leave = await leave_event_registration(session, event_id=event_id, user_id=user.id)
    if leave is None:
        raise HTTPException(status_code=404, detail="registration_not_found")
    if leave.outcome == "cannot_change":
        raise HTTPException(status_code=409, detail="cannot_change_plans")

    notice = None
    if leave.promoted is not None and bot is not None:
        promoted_user = await session.get(User, leave.promoted.user_id)
        if promoted_user is not None:
            notice = await enqueue_registration_notice(
                session, leave.promoted, promoted_user.telegram_id, RegistrationNoticeKind.PROMOTION
            )
    result = await _to_event_out(session, leave.event, leave.registration, user)
    await session.commit()
    if notice is not None and bot is not None:
        await deliver_registration_notice(session, notice, bot.send_message, settings)
    return result


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
    # Hide cancelled events from strangers before the not_registered oracle.
    event, _registration = await _require_participant_event(session, event_id, user)
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
