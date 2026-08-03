from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Task, TaskParticipant, User

ARCHIVE_STATUSES = {"completed", "cancelled", "rejected"}
ACTIVE_MEMBERSHIP_STATUSES = {"pending", "accepted", "joined"}
ACCEPTED_MEMBERSHIP_STATUSES = {"accepted", "joined"}


def matches_task_audience(task: Task, user: User) -> bool:
    role = (task.audience_filter_json or {}).get("role")
    return not role or role == user.role


async def get_membership(
    session: AsyncSession, task_id: int, user_id: int
) -> TaskParticipant | None:
    return await session.scalar(
        select(TaskParticipant).where(
            TaskParticipant.task_id == task_id, TaskParticipant.user_id == user_id
        )
    )


async def can_view(session: AsyncSession, task: Task, user: User) -> bool:
    if task.assignee_id == user.id:
        return True
    membership = await get_membership(session, task.id, user.id)
    if membership and membership.status in ACTIVE_MEMBERSHIP_STATUSES:
        return True
    return (
        task.task_type == "challenge"
        and task.status == "published"
        and matches_task_audience(task, user)
    )


async def can_submit(session: AsyncSession, task: Task, user: User) -> bool:
    if task.assignee_id == user.id:
        return True
    membership = await get_membership(session, task.id, user.id)
    return bool(membership and membership.status in ACCEPTED_MEMBERSHIP_STATUSES)


def is_joined_or_assigned(task: Task, joined_ids: set[int], user: User) -> bool:
    return task.assignee_id == user.id or task.id in joined_ids


def is_open_public_task(task: Task, joined_ids: set[int], user: User) -> bool:
    return (
        task.task_type == "challenge"
        and task.status == "published"
        and not is_joined_or_assigned(task, joined_ids, user)
        and matches_task_audience(task, user)
    )


async def list_for_user(session: AsyncSession, user: User) -> list[Task]:
    direct_tasks = (
        await session.scalars(
            select(Task).where(
                or_(
                    Task.assignee_id == user.id,
                    ((Task.task_type == "challenge") & (Task.status == "published")),
                )
            )
        )
    ).all()
    memberships = (
        await session.scalars(
            select(TaskParticipant).where(TaskParticipant.user_id == user.id)
        )
    ).all()
    tasks_by_id = {task.id: task for task in direct_tasks}
    joined_ids = {
        membership.task_id
        for membership in memberships
        if membership.status in ACTIVE_MEMBERSHIP_STATUSES
    }
    for membership in memberships:
        if membership.task_id in joined_ids:
            task = await session.get(Task, membership.task_id)
            if task:
                tasks_by_id[task.id] = task
    tasks = sorted(tasks_by_id.values(), key=lambda item: item.deadline)
    return [
        task
        for task in tasks
        if task.assignee_id == user.id
        or task.id in joined_ids
        or matches_task_audience(task, user)
    ]


async def joined_task_ids(
    session: AsyncSession, user: User, tasks: list[Task]
) -> set[int]:
    if not tasks:
        return {task.id for task in tasks if task.assignee_id == user.id}
    participants = (
        await session.scalars(
            select(TaskParticipant).where(
                TaskParticipant.user_id == user.id,
                TaskParticipant.task_id.in_([task.id for task in tasks]),
            )
        )
    ).all()
    joined = {
        item.task_id for item in participants if item.status in ACTIVE_MEMBERSHIP_STATUSES
    }
    joined.update(task.id for task in tasks if task.assignee_id == user.id)
    return joined


async def claim(
    session: AsyncSession, task: Task | None, user: User
) -> tuple[TaskParticipant | None, str | None]:
    """Join a published challenge task. Mirrors the Bot's task:join rule so
    both the Bot handler and the Mini App API enforce the same logic —
    see app/handlers/participant/task_block2.py."""
    if (
        task is None
        or task.task_type != "challenge"
        or task.status != "published"
        or not matches_task_audience(task, user)
    ):
        return None, "closed"
    current = (
        await session.scalars(
            select(TaskParticipant).where(TaskParticipant.task_id == task.id)
        )
    ).all()
    accepted = [item for item in current if item.status in ACCEPTED_MEMBERSHIP_STATUSES]
    if task.max_participants and len(accepted) >= task.max_participants:
        return None, "full"
    existing = next((item for item in current if item.user_id == user.id), None)
    if existing:
        if existing.status == "rejected":
            existing.status = "pending"
            return existing, None
        if existing.status == "pending":
            return existing, "already_pending"
        return existing, "already_joined"
    participant = TaskParticipant(task_id=task.id, user_id=user.id, status="pending")
    session.add(participant)
    await session.flush()
    return participant, None
