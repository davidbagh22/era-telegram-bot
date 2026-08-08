from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, RewardItem, Task
from app.utils.constants import EventStatus, TaskStatus

ACTIVE_EVENT_STATUSES = {
    EventStatus.APPROVED,
    EventStatus.PUBLISHED,
    EventStatus.REGISTRATION_OPEN,
    EventStatus.REGISTRATION_CLOSED,
    EventStatus.ACTIVE,
}

ACTIVE_TASK_STATUSES = {
    TaskStatus.NEW,
    TaskStatus.PUBLISHED,
    TaskStatus.IN_PROGRESS,
    TaskStatus.REVIEW,
}


def event_hide_date(event: Event, hide_after_days: int = 1) -> date:
    return event.event_date + timedelta(days=hide_after_days)


def event_is_visible(event: Event, today: date | None = None) -> bool:
    today = today or date.today()
    return event.status in {EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN} and event.event_date >= today


def task_is_active(task: Task, now: datetime | None = None) -> bool:
    now = now or datetime.now().astimezone()
    return task.status in ACTIVE_TASK_STATUSES and task.deadline > now


def reward_is_active(reward: RewardItem) -> bool:
    return bool(reward.is_active and (reward.quantity is None or reward.quantity > 0))


async def archive_expired_content(
    session: AsyncSession,
    *,
    timezone: str,
    event_hide_after_days: int = 1,
) -> dict[str, int]:
    now = datetime.now(ZoneInfo(timezone))
    today = now.date()
    archived_events = 0
    archived_tasks = 0
    hidden_rewards = 0

    events = (
        await session.scalars(
            select(Event).where(Event.status.in_(list(ACTIVE_EVENT_STATUSES)))
        )
    ).all()
    for event in events:
        if event_hide_date(event, event_hide_after_days) < today:
            event.status = EventStatus.COMPLETED
            archived_events += 1

    tasks = (
        await session.scalars(
            select(Task).where(Task.status.in_(list(ACTIVE_TASK_STATUSES)))
        )
    ).all()
    for task in tasks:
        if task.deadline <= now:
            task.status = TaskStatus.OVERDUE
            archived_tasks += 1

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
        hidden_rewards += 1

    return {
        "events": archived_events,
        "tasks": archived_tasks,
        "rewards": hidden_rewards,
    }
