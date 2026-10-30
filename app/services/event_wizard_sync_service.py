from __future__ import annotations

from datetime import datetime
import logging

from sqlalchemy import select

from app.database.event_experience import EventExperience
from app.database.models import Event, EventActivity
from app.utils.constants import EventStatus

logger = logging.getLogger(__name__)

PUBLIC_STATUSES = {
    EventStatus.APPROVED,
    EventStatus.PUBLISHED,
    EventStatus.REGISTRATION_OPEN,
    EventStatus.REGISTRATION_CLOSED,
    EventStatus.ACTIVE,
    EventStatus.COMPLETED,
}


def _deadline(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _validated_task_configuration(experience) -> tuple[list[dict], list[int]] | None:
    """Reject malformed legacy JSON without touching its activity or point rows."""
    # Only SQL NULL represents an absent legacy configuration. Empty JSON
    # objects, strings, numbers and booleans are malformed, even if falsey:
    # treating them as [] could deactivate existing activities or create
    # duplicates when the stored activity-id vector is corrupted.
    tasks = experience.participant_tasks
    ids = experience.participant_task_activity_ids
    if tasks is None:
        tasks = []
    if ids is None:
        ids = []
    if not isinstance(tasks, list) or not isinstance(ids, list):
        return None
    configured: list[dict] = []
    for item in tasks:
        if not isinstance(item, dict):
            return None
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        # EventActivity.title is VARCHAR(255), points is PostgreSQL INTEGER.
        # Reject the entire malformed row before writing any of its tasks.
        if len(title) > 255:
            return None
        try:
            points = int(item.get("points") or 0)
        except (TypeError, ValueError, OverflowError):
            return None
        if points > 2_147_483_647:
            return None
        configured.append(item)
    old_ids: list[int] = []
    for value in ids:
        # Never compact an invalid/empty slot: the vector is positional, so
        # skipping one entry could reassign a different participant task and
        # change its points/review policy. Reject duplicate IDs as well.
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            activity_id = value
        elif (
            isinstance(value, str)
            and 0 < len(value.strip()) <= 10
            and value.strip().isascii()
            and value.strip().isdecimal()
        ):
            activity_id = int(value.strip())
        else:
            return None
        if not 0 < activity_id <= 2_147_483_647 or activity_id in old_ids:
            return None
        old_ids.append(activity_id)
    return configured, old_ids


async def sync_event_wizard_tasks(session) -> int:
    """Keep participant tasks from the event wizard actionable and idempotent.

    EventExperience stores the editor-friendly JSON. This synchronizer turns
    each configured task into the existing EventActivity workflow so
    participants can actually submit/complete it and receive points. The
    stored activity-id vector means edits update the same rows instead of
    creating duplicates.
    """
    rows = (
        await session.execute(
            select(Event, EventExperience)
            .join(EventExperience, EventExperience.event_id == Event.id)
            .where(
                EventExperience.is_complete.is_(True),
                Event.status.in_(PUBLIC_STATUSES),
            )
            .order_by(Event.id)
        )
    ).all()
    changed = 0
    for event, experience in rows:
        # The initial scan is intentionally not a lock: a concurrent worker
        # may have materialised these tasks after we read it. Lock the single
        # companion row, then refresh its JSON *under the lock* before deciding
        # whether to insert or deactivate any EventActivity rows. Consistent
        # event-id order avoids competing scheduler workers locking rows in
        # opposite orders. SQLite ignores FOR UPDATE; the PostgreSQL race
        # probe is the concurrency acceptance gate.
        experience = await session.scalar(
            select(EventExperience)
            .where(EventExperience.event_id == event.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if experience is None or not experience.is_complete:
            continue
        await session.refresh(event, attribute_names=["status"])
        if event.status not in PUBLIC_STATUSES:
            continue
        configuration = _validated_task_configuration(experience)
        if configuration is None:
            logger.warning("Skipping malformed event wizard tasks event_id=%s", event.id)
            continue
        configured, old_ids = configuration
        new_ids: list[int] = []

        for index, item in enumerate(configured):
            activity = None
            if index < len(old_ids):
                candidate = await session.get(EventActivity, old_ids[index])
                if candidate is not None and candidate.event_id == event.id:
                    activity = candidate
            if activity is None:
                activity = EventActivity(
                    event_id=event.id,
                    title=str(item.get("title") or "").strip(),
                    description=str(item.get("description") or "").strip() or "Выполните задание мероприятия.",
                    submission_type="text" if bool(item.get("confirmation_required")) else "manual",
                    requires_review=bool(item.get("confirmation_required")),
                    points=max(0, int(item.get("points") or 0)),
                    deadline=_deadline(item.get("deadline")),
                    is_active=True,
                )
                session.add(activity)
                await session.flush()
                changed += 1
            else:
                next_values = {
                    "title": str(item.get("title") or "").strip(),
                    "description": str(item.get("description") or "").strip() or "Выполните задание мероприятия.",
                    "submission_type": "text" if bool(item.get("confirmation_required")) else "manual",
                    "requires_review": bool(item.get("confirmation_required")),
                    "points": max(0, int(item.get("points") or 0)),
                    "deadline": _deadline(item.get("deadline")),
                    "is_active": True,
                }
                if any(getattr(activity, key) != value for key, value in next_values.items()):
                    for key, value in next_values.items():
                        setattr(activity, key, value)
                    changed += 1
            new_ids.append(activity.id)

        for stale_id in old_ids[len(configured):]:
            stale = await session.get(EventActivity, stale_id)
            if stale is not None and stale.event_id == event.id and stale.is_active:
                stale.is_active = False
                changed += 1

        if new_ids != old_ids:
            experience.participant_task_activity_ids = new_ids
            changed += 1

    if changed:
        await session.commit()
    return changed


async def sync_event_wizard_tasks_job(session_factory) -> None:
    async with session_factory() as session:
        await sync_event_wizard_tasks(session)
