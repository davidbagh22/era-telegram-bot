from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventRegistration
from app.services.audit_service import audit
from app.utils.constants import EventStatus, RegistrationStatus


async def published_events(session: AsyncSession) -> list[Event]:
    return list(
        (
            await session.scalars(
                select(Event)
                .where(
                    Event.status.in_([EventStatus.APPROVED, EventStatus.PUBLISHED]),
                    Event.event_date >= date.today(),
                )
                .order_by(Event.event_date, Event.event_time)
            )
        ).all()
    )


async def available_places(session: AsyncSession, event: Event) -> str:
    if event.participant_limit is None:
        return "без ограничений"
    registered = int(
        await session.scalar(
            select(func.count())
            .select_from(EventRegistration)
            .where(
                EventRegistration.event_id == event.id,
                EventRegistration.status.not_in(
                    [RegistrationStatus.CANCELLED, RegistrationStatus.NOT_COMING]
                ),
            )
        )
        or 0
    )
    return str(max(0, event.participant_limit - registered))


async def register_for_event(
    session: AsyncSession, event: Event, user_id: int
) -> tuple[EventRegistration | None, str | None]:
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
    if (
        event.participant_limit is not None
        and int(await available_places(session, event)) <= 0
    ):
        return None, "full"
    if existing:
        existing.status = RegistrationStatus.REGISTERED
        registration = existing
    else:
        registration = EventRegistration(event_id=event.id, user_id=user_id)
        session.add(registration)
    await session.flush()
    await audit(
        session,
        actor_id=user_id,
        action="event.registered",
        entity_type="event",
        entity_id=event.id,
    )
    return registration, None


def event_datetime(event: Event, timezone: str) -> datetime:
    return datetime.combine(
        event.event_date, event.event_time, tzinfo=ZoneInfo(timezone)
    )
