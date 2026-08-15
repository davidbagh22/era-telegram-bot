from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import qrcode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventRegistration
from app.services.event_service import event_datetime
from app.services.points_service import add_points, make_idempotency_key
from app.utils.constants import EventStatus, RegistrationStatus

CHECKIN_OPEN_BEFORE = timedelta(hours=2)
CHECKIN_CLOSE_AFTER = timedelta(hours=6)
CHECKIN_EVENT_STATUSES = {
    EventStatus.APPROVED,
    EventStatus.PUBLISHED,
    EventStatus.REGISTRATION_OPEN,
    EventStatus.REGISTRATION_CLOSED,
    EventStatus.ACTIVE,
}
CHECKIN_REGISTRATION_STATUSES = {
    RegistrationStatus.REGISTERED,
    RegistrationStatus.WILL_COME,
    RegistrationStatus.ATTENDED,
}


@dataclass(frozen=True)
class CheckInResult:
    event: Event
    registration: EventRegistration
    already_attended: bool
    points_awarded: int


def qr_png(link: str) -> bytes:
    if not link.startswith("https://t.me/"):
        raise ValueError("attendance QR must point to Telegram")
    image = qrcode.make(link)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def checkin_window(event: Event, timezone_name: str) -> tuple[datetime, datetime]:
    starts_at = event_datetime(event, timezone_name)
    return starts_at - CHECKIN_OPEN_BEFORE, starts_at + CHECKIN_CLOSE_AFTER


async def check_in(
    session: AsyncSession,
    *,
    event_id: int,
    user_id: int,
    settings: Settings,
) -> CheckInResult:
    event = await session.get(Event, event_id)
    if event is None:
        raise ValueError("event_not_found")
    if event.status not in CHECKIN_EVENT_STATUSES:
        raise ValueError("event_not_open")

    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user_id,
        )
    )
    if registration is None:
        raise ValueError("not_registered")
    if registration.status not in CHECKIN_REGISTRATION_STATUSES:
        raise ValueError("registration_not_active")

    now = datetime.now(ZoneInfo(settings.timezone))
    opens_at, closes_at = checkin_window(event, settings.timezone)
    if now < opens_at:
        raise ValueError("too_early")
    if now > closes_at:
        raise ValueError("too_late")

    if registration.status == RegistrationStatus.ATTENDED:
        return CheckInResult(
            event=event,
            registration=registration,
            already_attended=True,
            points_awarded=0,
        )

    registration.status = RegistrationStatus.ATTENDED
    registration.last_confirmation_at = now
    points = max(0, int(event.points_for_visit or 0))
    if points:
        await add_points(
            session,
            user_id=user_id,
            points=points,
            reason=f"Посещение мероприятия: {event.title}",
            approved_by=event.responsible_id,
            related_event_id=event.id,
            source_type="event_attendance",
            source_id=registration.id,
            idempotency_key=make_idempotency_key("event_attendance", event.id, user_id),
        )
    await session.flush()
    return CheckInResult(
        event=event,
        registration=registration,
        already_attended=False,
        points_awarded=points,
    )
