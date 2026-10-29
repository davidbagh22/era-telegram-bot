from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration
from app.services.audit_service import audit
from app.services.digital_engagement_service import award_event_registration
from app.services.event_registration_policy import registration_is_closed
from app.utils.constants import EventStatus, RegistrationStatus

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


async def register_for_event(
    session: AsyncSession,
    event: Event,
    user_id: int,
    *,
    waitlist_enabled: bool = False,
) -> tuple[EventRegistration | None, str | None]:
    """Register a participant, or put them on the waitlist when configured.

    The event row is locked while capacity is checked, so two simultaneous
    registrations cannot consume the same last seat.
    """
    # Re-read the event under its row lock. Without populate_existing the
    # session identity map may retain a pre-lock status after an admin edit.
    locked_event = await session.scalar(
        select(Event).where(Event.id == event.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if locked_event is None:
        return None, "closed"
    event = locked_event
    if event.status not in REGISTRATION_ALLOWED_STATUSES:
        return None, "closed"

    # Registration policy must be checked after acquiring the event lock.
    # The UI / callback may have read a stale deadline or waitlist setting.
    # Lock the companion row too and refresh any identity-map cached state.
    experience = await session.scalar(
        select(EventExperience).where(EventExperience.event_id == event.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if experience is not None:
        if not experience.registration_required:
            return None, "registration_not_required"
        if registration_is_closed(experience):
            return None, "closed"
        waitlist_enabled = bool(experience.waitlist_enabled)
    else:
        # Legacy events have no waitlist policy; do not trust a stale caller
        # flag to enable waitlisting without a persisted companion row.
        waitlist_enabled = False

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
    if is_full and not waitlist_enabled:
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
    if event.participant_limit is None:
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
    await session.flush()
    await audit(
        session,
        actor_id=waiting.user_id,
        action="event.waitlist_promoted",
        entity_type="event",
        entity_id=event.id,
    )
    return waiting


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
