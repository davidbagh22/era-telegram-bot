from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventRegistration, PointTransaction
from app.utils.constants import RegistrationStatus

ACTIVE_REGISTRATION_STATUSES = {
    RegistrationStatus.REGISTERED,
    RegistrationStatus.WILL_COME,
    RegistrationStatus.ATTENDED,
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
