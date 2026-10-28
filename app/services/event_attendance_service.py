from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.event_attendance import EventAttendanceSession
from app.database.models import AppSetting, Event, EventRegistration, PortfolioItem, User
from app.services.activity_metrics_service import increment_metric
from app.services.activity_scoring_service import score_event_role_bonus
from app.services.audit_service import audit
from app.services.event_registration_service import event_points_already_awarded
from app.services.notification_service import safe_send_once
from app.services.points_service import add_points
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus
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
    confirmation_closed_at: datetime | None = None
    notified_count: int = 0


@dataclass(frozen=True)
class ParticipantAttendanceState:
    event: Event
    eligible: bool
    confirmation_open: bool
    confirmation_closed: bool
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
        select(Event).where(Event.id == event_id).with_for_update().execution_options(populate_existing=True)
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
            User.is_blocked.is_(False), User.is_archived.is_(False),
            User.application_status == ApplicationStatus.APPROVED,
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
    # Stage in the caller's event transaction. A rollback must not tell people
    # that an event started/completed when the lifecycle write did not persist.
    if bot is None:
        return 0
    import json
    key = f'event-lifecycle:pending:{event.id}:{phase}'
    if await session.scalar(select(AppSetting.key).where(AppSetting.key == key)):
        return 0
    recipients = [participant.telegram_id for _, participant in await _registered_users(session, event.id)]
    payload = {'event_id': event.id, 'phase': phase, 'title': event.title, 'location': event.location,
               'recipients': recipients, 'status': 'pending', 'attempts': 0}
    session.add(AppSetting(key=key, value=json.dumps(payload, ensure_ascii=False)))
    await session.flush()
    return 0  # Delivery is asynchronous; do not claim queued messages were sent.


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
            and runtime.confirmation_closed_at is None
            and event.status in COMPLETED_STATUSES
        ),
        confirmation_closed_at=runtime.confirmation_closed_at if runtime else None,
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
                and runtime.confirmation_closed_at is None
                and event.status in COMPLETED_STATUSES
            ),
            confirmation_closed_at=runtime.confirmation_closed_at,
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
        confirmation_closed_at=runtime.confirmation_closed_at,
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
            confirmation_open=bool(runtime.attendance_code and runtime.confirmation_closed_at is None),
            confirmation_closed_at=runtime.confirmation_closed_at,
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
        confirmation_closed_at=None,
        notified_count=notified,
    )


async def close_confirmation(
    session: AsyncSession,
    event_id: int,
    *,
    actor_user_id: int,
) -> LifecycleState:
    """Close self-service claims without changing attendance or rewards.

    Locking the event serializes this with confirmation requests.  Repeated
    calls are successful and retain the first close timestamp.
    """
    event = await _event_for_update(session, event_id)
    runtime = await _attendance_session(session, event.id, create=False)
    if runtime is None or runtime.completed_at is None or event.status not in COMPLETED_STATUSES:
        raise ValueError("event_not_completed")
    if runtime.confirmation_closed_at is None:
        runtime.confirmation_closed_at = datetime.now(timezone.utc)
        await audit(
            session,
            actor_id=actor_user_id,
            action="event.attendance_confirmation_closed",
            entity_type="event",
            entity_id=event.id,
            new_value={"confirmation_closed_at": runtime.confirmation_closed_at.isoformat()},
        )
        await session.flush()
    return LifecycleState(
        event=event,
        session=runtime,
        can_start=False,
        can_complete=False,
        confirmation_open=False,
        confirmation_closed_at=runtime.confirmation_closed_at,
    )


async def participant_state(
    session: AsyncSession,
    event_id: int,
    user_id: int,
) -> ParticipantAttendanceState:
    event = await session.get(Event, event_id)
    if event is None or event.status in {EventStatus.DRAFT, EventStatus.PENDING_APPROVAL}:
        # A retained registration must not expose moderation-only event state
        # through the participant attendance API.
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
        and runtime.confirmation_closed_at is None
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
        confirmation_closed=bool(runtime and runtime.confirmation_closed_at),
        confirmed=confirmed,
        points_awarded=points_awarded,
    )


async def confirm_attendance(
    session: AsyncSession,
    event_id: int,
    user_id: int,
    code: str,
) -> ConfirmationResult:
    active_user = await session.scalar(select(User.id).where(User.id == user_id,
        User.application_status == ApplicationStatus.APPROVED, User.is_blocked.is_(False), User.is_archived.is_(False)))
    if active_user is None:
        raise ValueError('participant_not_active')
    event = await _event_for_update(session, event_id)
    if event.status in {EventStatus.DRAFT, EventStatus.PENDING_APPROVAL}:
        # Check before reading retained registrations or making any writes.
        # A draft must be indistinguishable from a nonexistent event.
        raise ValueError("event_not_found")
    runtime = await _attendance_session(session, event.id, create=False)
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

    # A confirmed attendance is a terminal success even when an administrator
    # has since closed the claim window. This makes retries/reloads safe and
    # reports the durable state instead of turning success into an error.
    if registration.status == RegistrationStatus.ATTENDED:
        return ConfirmationResult(
            state=await participant_state(session, event.id, user_id),
            points_awarded=0,
            already_confirmed=True,
        )

    if (
        runtime is None
        or not runtime.attendance_code
        or runtime.completed_at is None
        or runtime.confirmation_closed_at is not None
        or event.status not in COMPLETED_STATUSES
    ):
        raise ValueError("attendance_not_open")

    supplied = normalize_code(code)
    expected = normalize_code(runtime.attendance_code)
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise ValueError("invalid_attendance_code")

    already_confirmed = registration.status == RegistrationStatus.ATTENDED
    registration.status = RegistrationStatus.ATTENDED
    registration.last_confirmation_at = datetime.now(timezone.utc)

    points = max(0, int(event.points_for_visit or 0))
    points_awarded = 0
    approved_by_id = runtime.completed_by or event.responsible_id
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
            approved_by=approved_by_id,
            related_event_id=event.id,
            source_type="event_attendance",
            source_id=registration.id,
            idempotency_key=f"event_attendance:{event.id}:{user_id}",
        )
        points_awarded = points

    # Event Scoring Profile (Points/Ranks ToR sections 16-20): bumps
    # events_attended and, if this participant took on a role beyond plain
    # attendance, their role bonus + the event's preset activity metrics.
    # Independently idempotent from the block above -- runs even when
    # points_for_visit is 0, and never re-fires on a repeat confirmation.
    if not already_confirmed:
        await increment_metric(session, user_id=user_id, metric_key="events_attended", delta=1)
    participant = await session.get(User, user_id)
    if participant is not None:
        await score_event_role_bonus(session, event, registration, participant, approved_by_id=approved_by_id)

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


def attendance_v2_enabled(settings, telegram_id: int) -> bool:
    mode = getattr(settings, 'feature_attendance_qr', 'OFF')
    return mode == 'ALL' or (mode == 'TESTERS' and telegram_id in (settings.attendance_qr_tester_ids or settings.feature_tester_ids))


def confirmation_payload(event_id: int, code: str) -> str:
    return f'attend2_{event_id}_{normalize_code(code)}'


def parse_confirmation_payload(payload: str) -> tuple[int, str] | None:
    import re
    match = re.fullmatch(r'attend2_([1-9][0-9]{0,9})_([A-Z2-9]{8})', payload)
    return (int(match[1]), match[2]) if match else None


def confirmation_qr_png(link: str) -> bytes:
    from io import BytesIO
    import segno
    output = BytesIO()
    segno.make_qr(link, error='m').save(output, kind='png', scale=8, border=4)
    return output.getvalue()


async def confirmation_qr(session: AsyncSession, event_id: int, *, settings, telegram_id: int) -> tuple[str, bytes]:
    if not attendance_v2_enabled(settings, telegram_id):
        raise ValueError('attendance_qr_disabled')
    state = await lifecycle_state(session, event_id)
    if not state.confirmation_open or state.session is None or not state.session.attendance_code:
        raise ValueError('attendance_not_open')
    link = f"https://t.me/{settings.bot_username or 'ERA_1bot'}?start={confirmation_payload(event_id, state.session.attendance_code)}"
    return link, confirmation_qr_png(link)


async def deliver_attendance_notifications(bot: Bot, settings, session_factory) -> int:
    import hashlib
    import json
    from html import escape
    from sqlalchemy import text
    async with session_factory() as session:
        keys = (await session.scalars(select(AppSetting.key).where(AppSetting.key.like('event-lifecycle:pending:%')))).all()
    delivered = 0
    for key in keys:
        async with session_factory() as session:
            if session.bind.dialect.name == 'postgresql':
                lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
                await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_id})
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
            if row is None:
                continue
            payload = json.loads(row.value) if isinstance(row.value, str) else row.value
            if payload.get('status') != 'pending':
                continue
            event = await session.get(Event, payload['event_id'])
            if event is None or event.status == EventStatus.CANCELLED or (payload['phase'] == 'start' and event.status in COMPLETED_STATUSES):
                payload['status'] = 'skipped'
                row.value = json.dumps(payload, ensure_ascii=False)
                row.key = key.replace(':pending:', ':'+payload['status']+':', 1)
                await session.commit()
                continue
            if payload['phase'] == 'complete' and not (await lifecycle_state(session, event.id)).confirmation_open:
                payload['status'] = 'skipped'
                row.value = json.dumps(payload, ensure_ascii=False)
                row.key = key.replace(':pending:', ':'+payload['status']+':', 1)
                await session.commit()
                continue
            eligible = {participant.telegram_id for _, participant in await _registered_users(session, event.id)}
            title = escape(payload['title'])
            body = (f'🔥 Мероприятие начинается\n\n{title}\n📍 {escape(payload["location"])}\n\n'
                    'Вы зарегистрированы. После завершения ведущий даст код или QR для подтверждения посещения.'
                    if payload['phase'] == 'start' else
                    f'✅ Мероприятие завершено\n\n{title}\n\nЕсли вы были на месте, получите код или QR у ведущего и подтвердите посещение. Баллы начисляются один раз.')
            retry = needs_attention = False
            for recipient in sorted(set(payload['recipients']) & eligible):
                keyboard = _event_button(settings.effective_miniapp_url, event.id)
                if payload['phase'] == 'complete' and attendance_v2_enabled(settings, recipient):
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text='✅ Ввести код посещения', callback_data=f'event:confirm_code:{event.id}')]])
                result = await safe_send_once(bot, settings, recipient, body,
                    delivery_key=f"event-lifecycle:{event.id}:{payload['phase']}:{recipient}", notification_type='event_lifecycle', reply_markup=keyboard, parse_mode='HTML')
                delivered += int(result.sent and not result.duplicate)
                if not result.sent and result.status not in {'blocked', 'unreachable', 'skipped'}:
                    if result.status in {'uncertain', 'conflict'}:
                        needs_attention = True
                    else:
                        retry = True
            payload['attempts'] = payload.get('attempts', 0) + 1
            payload['status'] = 'needs_attention' if needs_attention or (retry and payload['attempts'] >= 3) else 'pending' if retry else 'sent'
            row.value = json.dumps(payload, ensure_ascii=False)
            if payload['status'] != 'pending':
                row.key = key.replace(':pending:', ':'+payload['status']+':', 1)
            await session.commit()
    return delivered
