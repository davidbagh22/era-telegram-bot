from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Event,
    EventRegistration,
    PointTransaction,
    PortfolioItem,
    Task,
    User,
    UserDepartment,
    UserDirection,
)
from app.services import task_service
from app.services.event_registration_service import ACTIVE_REGISTRATION_STATUSES
from app.services.event_service import PUBLIC_EVENT_STATUSES
from app.utils.constants import RegistrationStatus, TaskStatus

EventScope = Literal["all", "for_me", "mine", "past"]
# DELTA ToR §8: restores "Для тебя" (deterministic recommendation, not AI
# ranking) and "Командные" (TEAM/SOLO_OR_TEAM claim-mode tasks) alongside
# the 4 scopes that already existed.
TaskScope = Literal["available", "for_you", "team", "mine", "review", "completed"]

# "for_me" is intentionally an alias of "all" for now: Event.access_type
# exists on the model but no audience-targeting rule reads it anywhere in
# the bot today. Personalizing this tab is real future work, not something
# to fake here — see docs/ERA_PLATFORM_PROGRESS.md.


async def list_events(
    session: AsyncSession, user: User, scope: EventScope
) -> list[tuple[Event, EventRegistration | None]]:
    if scope in ("all", "for_me"):
        events = list(
            (
                await session.scalars(
                    select(Event)
                    .where(
                        Event.status.in_(PUBLIC_EVENT_STATUSES),
                        Event.event_date >= date.today(),
                    )
                    .order_by(Event.event_date, Event.event_time)
                )
            ).all()
        )
        registrations = (
            await session.scalars(
                select(EventRegistration).where(
                    EventRegistration.user_id == user.id,
                    EventRegistration.event_id.in_([event.id for event in events] or [-1]),
                )
            )
        ).all()
        reg_by_event = {registration.event_id: registration for registration in registrations}
        return [(event, reg_by_event.get(event.id)) for event in events]

    if scope == "mine":
        rows = (
            await session.execute(
                select(Event, EventRegistration)
                .join(EventRegistration, EventRegistration.event_id == Event.id)
                .where(
                    EventRegistration.user_id == user.id,
                    EventRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES),
                    Event.event_date >= date.today(),
                )
                .order_by(Event.event_date, Event.event_time)
            )
        ).all()
        return [(event, registration) for event, registration in rows]

    rows = (
        await session.execute(
            select(Event, EventRegistration)
            .join(EventRegistration, EventRegistration.event_id == Event.id)
            .where(
                EventRegistration.user_id == user.id,
                Event.event_date < date.today(),
            )
            .order_by(Event.event_date.desc(), Event.event_time.desc())
        )
    ).all()
    return [(event, registration) for event, registration in rows]


async def _user_department_and_direction_ids(
    session: AsyncSession, user: User
) -> tuple[set[int], set[int]]:
    department_ids = set(
        (
            await session.scalars(
                select(UserDepartment.department_id).where(UserDepartment.user_id == user.id)
            )
        ).all()
    )
    direction_ids = set(
        (
            await session.scalars(
                select(UserDirection.direction_id).where(UserDirection.user_id == user.id)
            )
        ).all()
    )
    return department_ids, direction_ids


async def _for_you_tasks(
    session: AsyncSession, user: User, available: list[Task], *, limit: int = 12
) -> list[Task]:
    """Deterministic rules per DELTA ToR §9 (no AI ranking): prioritize a
    task that matches the participant's own department/direction, then
    break ties by nearest deadline (matches the "дедлайн" signal the ToR
    lists) -- the same shape as opportunity_service.recommended_offers's
    eligibility-first, deadline-second ordering, adapted for tasks."""
    department_ids, direction_ids = await _user_department_and_direction_ids(session, user)

    def score(task: Task) -> tuple[int, object]:
        matches = 0
        if task.direction_id is not None and task.direction_id in direction_ids:
            matches += 2
        if task.department_id is not None and task.department_id in department_ids:
            matches += 1
        return (-matches, task.deadline)

    return sorted(available, key=score)[:limit]


def _claim_mode(task: Task) -> str | None:
    reward = getattr(task, "reward_json", None) or {}
    return (reward.get("community_mission") or {}).get("claim_mode")


async def list_tasks(session: AsyncSession, user: User, scope: TaskScope) -> list[Task]:
    all_tasks = await task_service.list_for_user(session, user)
    joined_ids = await task_service.joined_task_ids(session, user, all_tasks)

    if scope == "available":
        return [
            task for task in all_tasks if task_service.is_open_public_task(task, joined_ids, user)
        ]
    if scope == "for_you":
        available = [
            task for task in all_tasks if task_service.is_open_public_task(task, joined_ids, user)
        ]
        return await _for_you_tasks(session, user, available)
    if scope == "team":
        available = [
            task for task in all_tasks if task_service.is_open_public_task(task, joined_ids, user)
        ]
        return [task for task in available if _claim_mode(task) in ("TEAM", "SOLO_OR_TEAM")]
    if scope == "mine":
        return [
            task
            for task in all_tasks
            if task.status not in task_service.ARCHIVE_STATUSES
            and task_service.is_joined_or_assigned(task, joined_ids, user)
        ]
    if scope == "review":
        return [
            task
            for task in all_tasks
            if task.status == TaskStatus.REVIEW
            and task_service.is_joined_or_assigned(task, joined_ids, user)
        ]
    return [
        task
        for task in all_tasks
        if task.status == TaskStatus.COMPLETED
        and task_service.is_joined_or_assigned(task, joined_ids, user)
    ]


@dataclass(frozen=True)
class CalendarItem:
    kind: str
    id: int
    title: str
    date: str
    time: str | None


async def calendar_items(
    session: AsyncSession, user: User, *, days_ahead: int = 60
) -> list[CalendarItem]:
    horizon = date.today() + timedelta(days=days_ahead)
    items: list[CalendarItem] = []

    event_rows = await list_events(session, user, "mine")
    for event, _ in event_rows:
        if event.event_date > horizon:
            continue
        items.append(
            CalendarItem(
                kind="event",
                id=event.id,
                title=event.title,
                date=event.event_date.isoformat(),
                time=event.event_time.isoformat(timespec="minutes"),
            )
        )

    for task in await list_tasks(session, user, "mine"):
        deadline_date = task.deadline.date()
        if deadline_date > horizon:
            continue
        items.append(
            CalendarItem(
                kind="task",
                id=task.id,
                title=task.title,
                date=deadline_date.isoformat(),
                time=task.deadline.strftime("%H:%M"),
            )
        )

    items.sort(key=lambda item: (item.date, item.time or ""))
    return items


@dataclass(frozen=True)
class HistoryEntry:
    kind: str
    title: str
    date: str
    detail: str


async def history_entries(session: AsyncSession, user: User, limit: int = 50) -> list[HistoryEntry]:
    entries: list[HistoryEntry] = []

    attended_rows = (
        await session.execute(
            select(Event, EventRegistration)
            .join(EventRegistration, EventRegistration.event_id == Event.id)
            .where(
                EventRegistration.user_id == user.id,
                EventRegistration.status == RegistrationStatus.ATTENDED,
            )
        )
    ).all()
    for event, _ in attended_rows:
        entries.append(
            HistoryEntry(
                kind="event_attended",
                title=event.title,
                date=event.event_date.isoformat(),
                detail=event.location,
            )
        )

    for task in await list_tasks(session, user, "completed"):
        entries.append(
            HistoryEntry(
                kind="task_completed",
                title=task.title,
                date=task.deadline.date().isoformat(),
                detail=f"{task.points} баллов",
            )
        )

    portfolio_items = (
        await session.scalars(
            select(PortfolioItem).where(
                PortfolioItem.user_id == user.id, PortfolioItem.status == "verified"
            )
        )
    ).all()
    for item in portfolio_items:
        entry_date = item.issued_at.isoformat() if item.issued_at else item.created_at.date().isoformat()
        entries.append(
            HistoryEntry(kind="portfolio", title=item.title, date=entry_date, detail=item.item_type)
        )

    points_rows = (
        await session.scalars(
            select(PointTransaction)
            .where(PointTransaction.user_id == user.id)
            .order_by(PointTransaction.created_at.desc())
            .limit(limit)
        )
    ).all()
    for transaction in points_rows:
        sign = "+" if transaction.points >= 0 else ""
        entries.append(
            HistoryEntry(
                kind="points",
                title=transaction.reason,
                date=transaction.created_at.date().isoformat(),
                detail=f"{sign}{transaction.points} баллов",
            )
        )

    entries.sort(key=lambda entry: entry.date, reverse=True)
    return entries[:limit]
