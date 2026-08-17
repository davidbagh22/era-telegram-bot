from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.event_attendance import EventAttendanceSession
from app.database.models import Event, EventRegistration, PortfolioItem, User
from app.services.audit_service import audit
from app.services.event_registration_service import event_points_already_awarded
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.utils.constants import EventStatus, RegistrationStatus
from app.utils.deep_links import miniapp_event_url

CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 8

STARTABLE_STATUSES = {
    EventStatus.APPROVED,
    EventStatus.PUBLISHED,
    EventStatus.REGISTRATION_OPEN,
    EventStatus.REGISTRATION_CLOSED,
}
COMPLETED_STATUSES = {EventStatus.COMPLETED, EventStatus.REPORT_SUBMITTED}
CONFIRMABLE_REGISTRATION_STATUSES = {
    RegistrationStatus.REGISTERED,
    RegistrationStatus.WILL_COME,
    RegistrationStatus.ATTENDED,
}
NOTIFICATION_REGISTRATION_STATUSES = {
    RegistrationStatus.REGISTERED,
    RegistrationStatus.WILL_COME,
}


@dataclass(frozen=True)
class LifecycleState:
    event: Event
    session: EventAttendanceSession | None
    can_start: bool
    can_complete: bool
    confirmation_open: bool
    notified_count: int = 0


@dataclass(frozen=True)
class ParticipantAttendanceState:
    event: Event
    eligible: bool
    confirmation_open: bool
    confirmed: bool
    points_awarded: bool


@dataclass(frozen=True)
class ConfirmationResult:
    state: ParticipantAttendanceState
    points_awarded: int
    already_confirmed: bool


def normalize_code(value: str) -> str:
    return "".join(character for character in value.upper().strip() if character.isalnum())


def generate_attendance_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


async def _unique_code(session: AsyncSession) -> str:
    for _ in range(12):
        code = generate_attendance_code()
        exists = await session.scalar(
            select(EventAttendanceSession.event_id).where(
                EventAttendanceSession.attendance_code == code
            )
        )
        if exists is None:
            return code
    raise RuntimeError("attendance_code_generation_failed")


async def _event_for_update(session: AsyncSession, event_id: int) -> Event:
    event = await session.scalar(
        select(Event).where(Event.id == event_id).with_for_update()
    )
    if event is None:
        raise ValueError("event_not_found")
    return event


async def _attendance_session(
    session: AsyncSession,
    event_id: int,
    *,
    create: bool,
) -> EventAttendanceSession | None:
    item = await session.get(EventAttendanceSession, event_id)
    if item is None and create:
        item = EventAttendanceSession(event_id=event_id)
        session.add(item)
        await session.flush()
    return item


async def _registered_users(
    session: AsyncSession,
    event_id: int,
) -> list[tuple[EventRegistration, User]]:
    result = await session.execute(
        select(EventRegistration, User)
        .join(User, User.id == EventRegistration.user_id)
        .where(
            EventRegistration.event_id == event_id,
            EventRegistration.status.in_(NOTIFICATION_REGISTRATION_STATUSES),
        )
        .order_by(EventRegistration.created_at)
    )
    return list(result.all())


def _event_button(miniapp_url: str, event_id: int) -> InlineKeyboardMarkup | None:
    url = miniapp_event_url(miniapp_url, event_id)
    if not url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть мероприятие",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


async def _notify_registered(
    session: AsyncSession,
    bot: Bot | None,
    event: Event,
    *,
    miniapp_url: str,
    phase: str,
) -> int:
    if bot is None:
        return 0
    rows = await _registered_users(session, event.id)
    keyboard = _event_button(miniapp_url, event.id)
    sent = 0
    for _registration, participant in rows:
        if phase == "start":
            text = (
                f"🔥 Мероприятие начинается\n\n{event.title}\n\n"
                f"📍 {event.location}\n\n"
                "Вы зарегистрированы. Если вы на месте — оставайтесь до конца: "
                "ведущие дадут код подтверждения присутствия. Поле для ввода появится "
                "в Mini App после завершения мероприятия."
            )
        else:
            text = (
                f"✅ Мероприятие завершено\n\n{event.title}\n\n"
                "Если вы были на месте, получите код у ведущего и введите его в карточке "
                "мероприятия в Mini App. После подтверждения баллы за посещение начислятся автоматически."
            )
        if await safe_send(
            bot,
            participant.telegram_id,
            text,
            keyboard,
        ):
            sent += 1
    return sent


async def lifecycle_state(
    session: AsyncSession,
    event_id: int,
) -> LifecycleState:
    event = await session.get(Event, event_id)
    if event is None:
        raise ValueError("event_not_found")
    runtime = await _attendance_session(session, event_id, create=False)
    return LifecycleState(
        event=event,
        session=runtime,
        can_start=event.status in STARTABLE_STATUSES,
        can_complete=event.status == EventStatus.ACTIVE,
        confirmation_open=bool(
            runtime
            and runtime.attendance_code
            and runtime.completed_at
            and event.status in COMPLETED_STATUSES
        ),
    )


async def start_event(
    session: AsyncSession,
    event_id: int,
    *,
    actor_user_id: int,
    bot: Bot | None,
    miniapp_url: str,
) -> LifecycleState:
    event = await _event_for_update(session, event_id)
    runtime = await _attendance_session(session, event.id, create=True)
    assert runtime is not None

    if runtime.started_at is not None:
        return LifecycleState(
            event=event,
            session=runtime,
            can_start=False,
            can_complete=event.status == EventStatus.ACTIVE,
            confirmation_open=bool(
                runtime.completed_at
                and runtime.attendance_code
                and event.status in COMPLETED_STATUSES
            ),
            notified_count=0,
        )
    if event.status not in STARTABLE_STATUSES and event.status != EventStatus.ACTIVE:
        raise ValueError("event_cannot_start")

    if runtime.attendance_code is None:
        runtime.attendance_code = await _unique_code(session)
    runtime.started_at = datetime.now(timezone.utc)
    runtime.started_by = actor_user_id
    event.status = EventStatus.ACTIVE
    await session.flush()

    await audit(
        session,
        actor_id=actor_user_id,
        action="event.started",
        entity_type="event",
        entity_id=event.id,
        new_value={"status": str(EventStatus.ACTIVE)},
    )
    notified = await _notify_registered(
        session,
        bot,
        event,
        miniapp_url=miniapp_url,
        phase="start",
    )
    return LifecycleState(
        event=event,
        session=runtime,
        can_start=False,
        can_complete=True,
        confirmation_open=False,
        notified_count=notified,
    )


async def complete_event(
    session: AsyncSession,
    event_id: int,
    *,
    actor_user_id: int,
    bot: Bot | None,
    miniapp_url: str,
) -> LifecycleState:
    event = await _event_for_update(session, event_id)
    runtime = await _attendance_session(session, event.id, create=True)
    assert runtime is not None

    if runtime.completed_at is not None and event.status in COMPLETED_STATUSES:
        return LifecycleState(
            event=event,
            session=runtime,
            can_start=False,
            can_complete=False,
            confirmation_open=bool(runtime.attendance_code),
            notified_count=0,
        )
    if event.status != EventStatus.ACTIVE:
        raise ValueError("event_not_active")

    if runtime.attendance_code is None:
        runtime.attendance_code = await _unique_code(session)
    if runtime.started_at is None:
        runtime.started_at = datetime.now(timezone.utc)
        runtime.started_by = actor_user_id
    runtime.completed_at = datetime.now(timezone.utc)
    runtime.completed_by = actor_user_id
    event.status = EventStatus.COMPLETED
    await session.flush()

    await audit(
        session,
        actor_id=actor_user_id,
        action="event.completed",
        entity_type="event",
        entity_id=event.id,
        new_value={"status": str(EventStatus.COMPLETED)},
    )
    notified = await _notify_registered(
        session,
        bot,
        event,
        miniapp_url=miniapp_url,
        phase="complete",
    )
    return LifecycleState(
        event=event,
        session=runtime,
        can_start=False,
        can_complete=False,
        confirmation_open=True,
        notified_count=notified,
    )


async def participant_state(
    session: AsyncSession,
    event_id: int,
    user_id: int,
) -> ParticipantAttendanceState:
    event = await session.get(Event, event_id)
    if event is None:
        raise ValueError("event_not_found")
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user_id,
        )
    )
    runtime = await _attendance_session(session, event_id, create=False)
    eligible = bool(
        registration and registration.status in CONFIRMABLE_REGISTRATION_STATUSES
    )
    confirmed = bool(
        registration and registration.status == RegistrationStatus.ATTENDED
    )
    confirmation_open = bool(
        eligible
        and not confirmed
        and runtime
        and runtime.attendance_code
        and runtime.completed_at
        and event.status in COMPLETED_STATUSES
    )
    points_awarded = False
    if registration is not None:
        points_awarded = await event_points_already_awarded(
            session,
            event_id=event.id,
            user_id=user_id,
        )
    return ParticipantAttendanceState(
        event=event,
        eligible=eligible,
        confirmation_open=confirmation_open,
        confirmed=confirmed,
        points_awarded=points_awarded,
    )


async def confirm_attendance(
    session: AsyncSession,
    event_id: int,
    user_id: int,
    code: str,
) -> ConfirmationResult:
    event = await _event_for_update(session, event_id)
    runtime = await _attendance_session(session, event.id, create=False)
    if (
        runtime is None
        or not runtime.attendance_code
        or runtime.completed_at is None
        or event.status not in COMPLETED_STATUSES
    ):
        raise ValueError("attendance_not_open")

    registration = await session.scalar(
        select(EventRegistration)
        .where(
            EventRegistration.event_id == event.id,
            EventRegistration.user_id == user_id,
        )
        .with_for_update()
    )
    if registration is None:
        raise ValueError("not_registered")
    if registration.status not in CONFIRMABLE_REGISTRATION_STATUSES:
        raise ValueError("registration_not_active")

    supplied = normalize_code(code)
    expected = normalize_code(runtime.attendance_code)
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise ValueError("invalid_attendance_code")

    already_confirmed = registration.status == RegistrationStatus.ATTENDED
    registration.status = RegistrationStatus.ATTENDED
    registration.last_confirmation_at = datetime.now(timezone.utc)

    points = max(0, int(event.points_for_visit or 0))
    points_awarded = 0
    if points and not await event_points_already_awarded(
        session,
        event_id=event.id,
        user_id=user_id,
    ):
        await add_points(
            session,
            user_id=user_id,
            points=points,
            reason=f"Посещение мероприятия: {event.title}",
            approved_by=runtime.completed_by or event.responsible_id,
            related_event_id=event.id,
            source_type="event_attendance",
            source_id=registration.id,
            idempotency_key=f"event_attendance:{event.id}:{user_id}",
        )
        points_awarded = points

    portfolio_exists = await session.scalar(
        select(PortfolioItem.id).where(
            PortfolioItem.user_id == user_id,
            PortfolioItem.related_event_id == event.id,
            PortfolioItem.item_type == "event",
        )
    )
    if portfolio_exists is None:
        from app.services.points_service import add_portfolio_item

        await add_portfolio_item(
            session,
            user_id=user_id,
            title=f"Участие: {event.title}",
            item_type="event",
            description="Посещение подтверждено кодом мероприятия ЭРА",
            issued_by=runtime.completed_by or event.responsible_id,
            related_event_id=event.id,
        )

    await session.flush()
    await audit(
        session,
        actor_id=user_id,
        action="event.attendance_confirmed",
        entity_type="event",
        entity_id=event.id,
        new_value={"registration_id": registration.id},
    )
    state = await participant_state(session, event.id, user_id)
    return ConfirmationResult(
        state=state,
        points_awarded=points_awarded,
        already_confirmed=already_confirmed,
    )
