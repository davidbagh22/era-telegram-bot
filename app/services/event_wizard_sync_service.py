from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.database.event_experience import EventExperience
from app.database.models import Event, EventActivity
from app.utils.constants import EventStatus

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
        )
    ).all()
    changed = 0
    for event, experience in rows:
        configured = [item for item in (experience.participant_tasks or []) if str(item.get("title") or "").strip()]
        old_ids = [int(value) for value in (experience.participant_task_activity_ids or []) if value]
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
                    created_by=event.created_by,
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
