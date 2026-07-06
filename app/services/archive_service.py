from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, RewardItem, Task
from app.utils.constants import EventStatus, TaskStatus

EVENT_STATUSES_TO_CLOSE = {
    EventStatus.PUBLISHED,
    EventStatus.REGISTRATION_OPEN,
    EventStatus.REGISTRATION_CLOSED,
    EventStatus.ACTIVE,
}

TASK_STATUSES_TO_CLOSE = {
    TaskStatus.NEW,
    TaskStatus.PUBLISHED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.REVIEW,
}


async def archive_expired_content(session: AsyncSession, *, timezone: str) -> dict[str, int]:
    now = datetime.now(ZoneInfo(timezone))
    today = now.date()

    events_count = 0
    tasks_count = 0
    rewards_count = 0

    events = (
        await session.scalars(
            select(Event).where(Event.status.in_(list(EVENT_STATUSES_TO_CLOSE)))
        )
    ).all()
    for event in events:
        if event.event_date < today:
            event.status = EventStatus.COMPLETED
            events_count += 1

    tasks = (
        await session.scalars(
            select(Task).where(Task.status.in_(list(TASK_STATUSES_TO_CLOSE)))
        )
    ).all()
    for task in tasks:
        if task.deadline <= now:
            task.status = TaskStatus.OVERDUE
            tasks_count += 1

    rewards = (
        await session.scalars(
            select(RewardItem).where(
                RewardItem.is_active.is_(True),
                RewardItem.quantity.is_not(None),
                RewardItem.quantity <= 0,
            )
        )
    ).all()
    for reward in rewards:
        reward.is_active = False
        rewards_count += 1

    return {"events": events_count, "tasks": tasks_count, "rewards": rewards_count}
