import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration
from app.services.audit_service import audit
from app.services.digital_engagement_service import award_event_registration
from app.services.event_registration_policy import registration_is_closed
from app.utils.constants import EventStatus, RegistrationStatus

logger = logging.getLogger(__name__)

PUBLIC_EVENT_STATUSES = {
    EventStatus.APPROVED,
    EventStatus.PUBLISHED,
    EventStatus.REGISTRATION_OPEN,
    EventStatus.REGISTRATION_CLOSED,
}

REGISTRATION_ALLOWED_STATUSES = {
    EventStatus.APPROVED,
    EventStatus.PUBLISHED,
    EventStatus.REGISTRATION_OPEN,
}

EVENT_STATUS_TRANSITIONS = {
    EventStatus.PUBLISHED: {EventStatus.REGISTRATION_OPEN},
    EventStatus.REGISTRATION_OPEN: {
        EventStatus.REGISTRATION_CLOSED,
        EventStatus.ACTIVE,
    },
    EventStatus.REGISTRATION_CLOSED: {EventStatus.ACTIVE},
    EventStatus.ACTIVE: {EventStatus.COMPLETED},
}


async def published_events(session: AsyncSession) -> list[Event]:
    return list(
        (
            await session.scalars(
                select(Event)
                .where(
                    Event.status.in_(PUBLIC_EVENT_STATUSES),
                    Event.event_date >= date.today(),
                )
                .order_by(Event.event_date, Event.event_time)
            )
        ).all()
    )


async def registered_count(session: AsyncSession, event_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(EventRegistration)
            .where(
                EventRegistration.event_id == event_id,
                EventRegistration.status.in_(
                    [
                        RegistrationStatus.REGISTERED,
                        RegistrationStatus.WILL_COME,
                        RegistrationStatus.ATTENDED,
                    ]
                ),
            )
        )
        or 0
    )


async def available_places(session: AsyncSession, event: Event) -> str:
    if event.participant_limit is None:
        return "без ограничений"
    registered = await registered_count(session, event.id)
    return str(max(0, event.participant_limit - registered))


async def _lock_event_for_capacity(session: AsyncSession, event_id: int) -> Event | None:
    # Refresh any cached capacity and acquire the event lock before flushing
    # a pending cancellation, which would otherwise lock its registration first.
    return await session.scalar(
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True, autoflush=False)
    )


async def register_for_event(
    session: AsyncSession,
    event: Event,
    user_id: int,
) -> tuple[EventRegistration | None, str | None]:
    """Register a participant, or put them on the waitlist when configured.

    The event row is locked while capacity is checked, so two simultaneous
    registrations cannot consume the same last seat.
    """
    locked_event = await _lock_event_for_capacity(session, event.id)
    if locked_event is None:
        return None, "closed"
    event = locked_event
    from app.services.anniversary_campaign_service import is_anniversary
    if is_anniversary(event):
        return None, "guest_registration_required"
    if event.status not in REGISTRATION_ALLOWED_STATUSES:
        return None, "closed"
    # The admin event editor takes the same Event lock before updating or
    # inserting the policy. Refresh the session cache after acquiring it.
    experience = await session.get(EventExperience, event.id, populate_existing=True)
    if registration_is_closed(experience):
        return None, "closed"
    if experience is not None and not experience.registration_required:
        return None, "registration_not_required"
    existing = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event.id,
            EventRegistration.user_id == user_id,
        )
    )
    if existing and existing.status not in (
        RegistrationStatus.CANCELLED,
        RegistrationStatus.NOT_COMING,
    ):
        return None, "already"

    is_full = (
        event.participant_limit is not None
        and int(await available_places(session, event)) <= 0
    )
    if is_full and not (experience and experience.waitlist_enabled):
        return None, "full"

    target_status = RegistrationStatus.WAITLIST if is_full else RegistrationStatus.REGISTERED
    if existing:
        existing.status = target_status
        registration = existing
    else:
        registration = EventRegistration(
            event_id=event.id,
            user_id=user_id,
            status=target_status,
        )
        session.add(registration)
    registration.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await audit(
        session,
        actor_id=user_id,
        action=("event.waitlisted" if target_status == RegistrationStatus.WAITLIST else "event.registered"),
        entity_type="event",
        entity_id=event.id,
    )
    # Digital-engagement bonus (ToR section 5): once per unique event ever,
    # regardless of how many times the person registers/cancels/re-registers
    # -- award_event_registration's idempotency key is keyed on event+user,
    # not on this call.
    await award_event_registration(session, user_id=user_id, event_id=event.id)
    return registration, None


async def promote_waitlist(session: AsyncSession, event: Event) -> EventRegistration | None:
    """Move the oldest waiting participant into a freed seat, if possible."""
    locked_event = await _lock_event_for_capacity(session, event.id)
    if locked_event is None or locked_event.participant_limit is None:
        return None
    event = locked_event
    from app.services.anniversary_campaign_service import is_anniversary
    if is_anniversary(event):
        return None
    if int(await available_places(session, event)) <= 0:
        return None
    waiting = await session.scalar(
        select(EventRegistration)
        .where(
            EventRegistration.event_id == event.id,
            EventRegistration.status == RegistrationStatus.WAITLIST,
        )
        .order_by(EventRegistration.created_at)
        .with_for_update()
        .limit(1)
    )
    if waiting is None:
        return None
    waiting.status = RegistrationStatus.REGISTERED
    waiting.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await audit(
        session,
        actor_id=waiting.user_id,
        action="event.waitlist_promoted",
        entity_type="event",
        entity_id=event.id,
    )
    return waiting


async def send_committed_registration_notice(
    session: AsyncSession,
    registration_id: int,
    expected_status: str,
    send: Callable[[], Awaitable[object]],
) -> None:
    """Check the committed state in a short transaction before an interactive reply."""
    try:
        async with session.begin():
            current = await session.scalar(
                select(EventRegistration.id)
                .join(Event, Event.id == EventRegistration.event_id)
                .where(
                    EventRegistration.id == registration_id,
                    EventRegistration.status == expected_status,
                    Event.status.notin_((EventStatus.DRAFT, EventStatus.PENDING_APPROVAL, EventStatus.CANCELLED)),
                )
            )
        if current is not None:
            await send()
    except Exception:
        logger.exception("Could not deliver committed registration notice for registration %s", registration_id)


def event_datetime(event: Event, timezone: str) -> datetime:
    return datetime.combine(
        event.event_date, event.event_time, tzinfo=ZoneInfo(timezone)
    )


def can_change_event_status(current: str, target: str) -> bool:
    try:
        current_status = EventStatus(current)
        target_status = EventStatus(target)
    except ValueError:
        return False
    return target_status in EVENT_STATUS_TRANSITIONS.get(current_status, set())
