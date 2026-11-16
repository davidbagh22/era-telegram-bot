"""Auto-archive elapsed events using the existing COMPLETED status.

Archiving removes an event from the public board. It is not attendance
confirmation and never deletes registrations, visits, or points.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.event_attendance import EventAttendanceSession
from app.database.event_experience import EventExperience
from app.database.models import Event
from app.services.audit_service import audit
from app.utils.constants import EventStatus

logger = logging.getLogger(__name__)

# Public / live board statuses that should leave the afisha after the end
# window. COMPLETED / REPORT_SUBMITTED / CANCELLED / drafts stay untouched.
_ARCHIVABLE_STATUSES = (
    EventStatus.APPROVED,
    EventStatus.PUBLISHED,
    EventStatus.REGISTRATION_OPEN,
    EventStatus.REGISTRATION_CLOSED,
    EventStatus.ACTIVE,
)

ARCHIVE_GRACE = timedelta(hours=24)
ATTENDANCE_CONFIRMATION_WINDOW = timedelta(days=7)
PROJECT_ACCELERATOR_TITLE = "Проектный акселератор"


def event_end_datetime(event: Event, experience: EventExperience | None, timezone: str) -> datetime:
    zone = ZoneInfo(timezone)
    end_clock = experience.end_time if experience and experience.end_time else event.event_time
    return datetime.combine(event.event_date, end_clock, tzinfo=zone)


async def archive_elapsed_events(
    session: AsyncSession,
    *,
    timezone: str = "Asia/Yerevan",
    now: datetime | None = None,
    actor_user_id: int | None = None,
) -> list[int]:
    """Move elapsed board events to COMPLETED. Idempotent; data-preserving."""
    zone = ZoneInfo(timezone)
    moment = now.astimezone(zone) if now else datetime.now(zone)
    cutoff = moment - ARCHIVE_GRACE

    rows = list(
        (
            await session.execute(
                select(Event, EventExperience)
                .outerjoin(EventExperience, EventExperience.event_id == Event.id)
                .where(Event.status.in_(_ARCHIVABLE_STATUSES))
            )
        ).all()
    )

    archived_ids: list[int] = []
    for event, experience in rows:
        end_at = event_end_datetime(event, experience, timezone)
        force_accelerator = event.title.strip() == PROJECT_ACCELERATOR_TITLE
        if not force_accelerator and end_at > cutoff:
            continue

        previous = event.status
        event.status = EventStatus.COMPLETED
        await session.flush()
        await audit(
            session,
            actor_id=actor_user_id,
            action="event.auto_archived",
            entity_type="event",
            entity_id=event.id,
            old_value={"status": previous},
            new_value={
                "status": str(EventStatus.COMPLETED),
                "end_at": end_at.isoformat(),
                "archived_at": moment.isoformat(),
            },
        )
        archived_ids.append(event.id)

    if archived_ids:
        logger.info("Auto-archived %s events: %s", len(archived_ids), archived_ids)
    return archived_ids


async def close_elapsed_attendance_windows(
    session: AsyncSession,
    *,
    timezone: str = "Asia/Yerevan",
    now: datetime | None = None,
    actor_user_id: int | None = None,
) -> list[int]:
    """Close self-service attendance claims 7 days after event end.

    Organizers confirm within this window; administrators may still correct
    attendance later through existing admin endpoints.
    """
    zone = ZoneInfo(timezone)
    moment = now.astimezone(zone) if now else datetime.now(zone)
    closed_ids: list[int] = []

    rows = list(
        (
            await session.execute(
                select(Event, EventExperience, EventAttendanceSession)
                .join(EventAttendanceSession, EventAttendanceSession.event_id == Event.id)
                .outerjoin(EventExperience, EventExperience.event_id == Event.id)
                .where(
                    Event.status.in_((EventStatus.COMPLETED, EventStatus.REPORT_SUBMITTED)),
                    EventAttendanceSession.confirmation_closed_at.is_(None),
                    EventAttendanceSession.attendance_code.is_not(None),
                )
            )
        ).all()
    )
    for event, experience, runtime in rows:
        end_at = event_end_datetime(event, experience, timezone)
        if moment < end_at + ATTENDANCE_CONFIRMATION_WINDOW:
            continue
        runtime.confirmation_closed_at = moment.astimezone(ZoneInfo("UTC"))
        await session.flush()
        await audit(
            session,
            actor_id=actor_user_id,
            action="event.attendance_confirmation_auto_closed",
            entity_type="event",
            entity_id=event.id,
            new_value={"confirmation_closed_at": runtime.confirmation_closed_at.isoformat()},
        )
        closed_ids.append(event.id)
    return closed_ids


async def run_event_archive_jobs(
    session_factory,
    *,
    timezone: str = "Asia/Yerevan",
) -> None:
    from app.services.media_service import rewrite_formulaic_media_task_titles

    async with session_factory() as session:
        async with session.begin():
            await archive_elapsed_events(session, timezone=timezone)
            await close_elapsed_attendance_windows(session, timezone=timezone)
            await rewrite_formulaic_media_task_titles(session)
