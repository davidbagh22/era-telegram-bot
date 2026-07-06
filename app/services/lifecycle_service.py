from __future__ import annotations

from datetime import date, datetime

from app.database.models import Event, RewardItem, Task
from app.utils.constants import EventStatus, TaskStatus

VISIBLE_EVENT_STATUSES = {EventStatus.PUBLISHED.value, EventStatus.REGISTRATION_OPEN.value}
ACTIVE_TASK_STATUSES = {
    TaskStatus.NEW.value,
    TaskStatus.PUBLISHED.value,
    TaskStatus.IN_PROGRESS.value,
    TaskStatus.REVIEW.value,
}


def _value(status: object) -> str:
    return getattr(status, "value", str(status))


def event_is_visible(event: Event, today: date | None = None) -> bool:
    today = today or date.today()
    return _value(event.status) in VISIBLE_EVENT_STATUSES and event.event_date >= today


def task_is_active(task: Task, now: datetime | None = None) -> bool:
    now = now or datetime.now().astimezone()
    return _value(task.status) in ACTIVE_TASK_STATUSES and task.deadline > now


def reward_is_active(reward: RewardItem) -> bool:
    return bool(reward.is_active and (reward.quantity is None or reward.quantity > 0))
