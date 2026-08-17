from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventRegistration, PointTransaction, User
from app.services.activity_scoring_service import score_event_attendance_and_role
from app.utils.constants import EventStatus, RegistrationStatus

# Events an admin can still run operations on after moderation — mirrors
# app/handlers/admin/event_registration_block14.py, which never gated this
# on status at all; excluding draft/pending/cancelled here just skips
# events that plainly have no attendance to manage yet or ever will.
OPERATIONAL_EVENT_STATUSES = (
    EventStatus.APPROVED,
    EventStatus.PUBLISHED,
    EventStatus.REGISTRATION_OPEN,
    EventStatus.REGISTRATION_CLOSED,
    EventStatus.ACTIVE,
    EventStatus.COMPLETED,
    EventStatus.REPORT_SUBMITTED,
)

ACTIVE_REGISTRATION_STATUSES = {
    RegistrationStatus.REGISTERED,
    RegistrationStatus.WILL_COME,
    RegistrationStatus.ATTENDED,
}

CHANGEABLE_EVENT_STATUSES_BLOCKED = {
    EventStatus.COMPLETED,
    EventStatus.CANCELLED,
    EventStatus.REPORT_SUBMITTED,
}


async def registration_count(session: AsyncSession, event_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(EventRegistration)
            .where(
                EventRegistration.event_id == event_id,
                EventRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
        )
        or 0
    )


async def registration_stats(session: AsyncSession, event: Event) -> dict[str, int | str]:
    registered = await registration_count(session, event.id)
    free: int | str
    if event.participant_limit is None:
        free = "без ограничений"
    else:
        free = max(0, event.participant_limit - registered)
    return {"registered": registered, "free": free}


async def event_points_already_awarded(
    session: AsyncSession, *, event_id: int, user_id: int
) -> bool:
    transaction_id = await session.scalar(
        select(PointTransaction.id).where(
            PointTransaction.related_event_id == event_id,
            PointTransaction.user_id == user_id,
            PointTransaction.points > 0,
        )
    )
    return transaction_id is not None


def can_change_registration_plans(registration: EventRegistration, event: Event) -> bool:
    """True if the participant can still tell us their plans changed.

    Shared by the Bot handler and the Mini App API so both enforce the same
    rule — see app/handlers/participant/event_plans_changed.py.
    """
    return (
        registration.status in {RegistrationStatus.REGISTERED, RegistrationStatus.WILL_COME}
        and event.status not in CHANGEABLE_EVENT_STATUSES_BLOCKED
    )


def mark_not_coming(registration: EventRegistration, event: Event) -> bool:
    """Cancel a registration if the rules allow it. Returns whether it changed."""
    if not can_change_registration_plans(registration, event):
        return False
    registration.status = RegistrationStatus.NOT_COMING
    return True


async def list_operational_events(session: AsyncSession) -> list[Event]:
    return list(
        (
            await session.scalars(
                select(Event)
                .where(Event.status.in_(OPERATIONAL_EVENT_STATUSES))
                .order_by(Event.event_date.desc())
            )
        ).all()
    )


async def list_participants(
    session: AsyncSession, event_id: int
) -> list[tuple[EventRegistration, User]]:
    result = await session.execute(
        select(EventRegistration, User)
        .join(User, User.id == EventRegistration.user_id)
        .where(EventRegistration.event_id == event_id)
        .order_by(EventRegistration.created_at)
    )
    return list(result.all())


def set_attendance(registration: EventRegistration, attended: bool) -> None:
    registration.status = RegistrationStatus.ATTENDED if attended else RegistrationStatus.NO_SHOW


async def award_attendance_points(
    session: AsyncSession, event: Event, *, approved_by_id: int | None
) -> list[User]:
    """Awards event.points_for_visit to every ATTENDED registration that
    hasn't already been paid — mirrors
    app/handlers/admin/event_registration_block14.py::award_event_points
    exactly, including its idempotency key, so re-running this (e.g. after
    marking one more person attended) never double-pays anyone. Returns the
    participants newly awarded, so the caller can notify them."""
    rows = await list_participants(session, event.id)
    newly_awarded: list[User] = []
    for registration, participant in rows:
        if registration.status != RegistrationStatus.ATTENDED:
            continue
        if await event_points_already_awarded(session, event_id=event.id, user_id=participant.id):
            continue
        await score_event_attendance_and_role(
            session, event, registration, participant, approved_by_id=approved_by_id
        )
        newly_awarded.append(participant)
    return newly_awarded
