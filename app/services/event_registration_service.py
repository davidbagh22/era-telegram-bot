from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventRegistration, PointTransaction
from app.utils.constants import EventStatus, RegistrationStatus

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
