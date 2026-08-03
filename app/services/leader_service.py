from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Event,
    Project,
    Task,
    TaskParticipant,
    User,
    UserDepartment,
    UserDirection,
)
from app.services.audit_service import audit
from app.services.notification_service import safe_send
from app.utils.constants import ApplicationStatus, Role

OPEN_TASK_TYPE = "challenge"


def scope_ids(user: User) -> tuple[set[int], set[int]]:
    return (
        {item.department_id for item in user.departments},
        {item.direction_id for item in user.directions},
    )


async def list_scope_participants(session: AsyncSession, user: User) -> list[User]:
    if user.role == Role.ADMIN:
        query = select(User).where(User.application_status == ApplicationStatus.APPROVED)
    else:
        department_ids, direction_ids = scope_ids(user)
        query = (
            select(User)
            .outerjoin(UserDepartment)
            .outerjoin(UserDirection)
            .where(
                User.application_status == ApplicationStatus.APPROVED,
                or_(
                    UserDepartment.department_id.in_(department_ids or {-1}),
                    UserDirection.direction_id.in_(direction_ids or {-1}),
                ),
            )
        )
    rows = await session.scalars(query.order_by(User.first_name))
    return list(rows.unique().all())


async def list_scope_events(session: AsyncSession, user: User) -> list[Event]:
    query = select(Event)
    if user.role != Role.ADMIN:
        department_ids, direction_ids = scope_ids(user)
        query = query.where(
            or_(
                Event.department_id.in_(department_ids or {-1}),
                Event.direction_id.in_(direction_ids or {-1}),
                Event.created_by == user.id,
            )
        )
    rows = await session.scalars(query.order_by(Event.event_date.desc()).limit(30))
    return list(rows.all())


async def list_scope_projects(session: AsyncSession, user: User) -> list[Project]:
    query = select(Project)
    if user.role != Role.ADMIN:
        department_ids, direction_ids = scope_ids(user)
        query = query.where(
            or_(
                Project.department_id.in_(department_ids or {-1}),
                Project.direction_id.in_(direction_ids or {-1}),
            )
        )
    rows = await session.scalars(query.order_by(Project.created_at.desc()).limit(30))
    return list(rows.all())


async def list_created_tasks(session: AsyncSession, user: User) -> list[Task]:
    rows = await session.scalars(
        select(Task).where(Task.creator_id == user.id).order_by(Task.deadline).limit(30)
    )
    return list(rows.all())


async def create_assigned_task(
    session: AsyncSession,
    *,
    creator: User,
    assignee: User,
    title: str,
    description: str,
    deadline: datetime,
    points: int,
    bot: Bot | None,
) -> Task:
    if not 0 <= points <= 1000:
        raise ValueError("invalid_points")
    task = Task(
        title=title,
        description=description,
        assignee_id=assignee.id,
        creator_id=creator.id,
        deadline=deadline,
        points=points,
    )
    session.add(task)
    await session.flush()
    if bot is not None:
        await safe_send(
            bot,
            assignee.telegram_id,
            f"У Вас новая задача ЭРА.\n\n{task.title}\n{task.description}\n\n"
            f"Дедлайн: {task.deadline:%d.%m.%Y %H:%M}",
        )
    await audit(
        session, actor_id=creator.id, action="task.created", entity_type="task", entity_id=task.id
    )
    return task


async def create_open_task(
    session: AsyncSession,
    *,
    creator: User,
    title: str,
    description: str,
    deadline: datetime,
    points: int,
    max_participants: int,
) -> Task:
    if not 0 <= points <= 1000:
        raise ValueError("invalid_points")
    if not 1 <= max_participants <= 50:
        raise ValueError("invalid_max_participants")
    task = Task(
        title=title,
        description=description,
        assignee_id=None,
        creator_id=creator.id,
        deadline=deadline,
        points=points,
        task_type=OPEN_TASK_TYPE,
        status="published",
        max_participants=max_participants,
    )
    session.add(task)
    await session.flush()
    await audit(
        session,
        actor_id=creator.id,
        action="task.open_published",
        entity_type="task",
        entity_id=task.id,
    )
    return task


@dataclass(frozen=True)
class OpenTaskApplication:
    participant: TaskParticipant
    applicant: User


@dataclass(frozen=True)
class OpenTaskWithApplications:
    task: Task
    applications: list[OpenTaskApplication]


async def list_open_tasks_with_applications(
    session: AsyncSession, user: User
) -> list[OpenTaskWithApplications]:
    tasks = await session.scalars(
        select(Task)
        .where(Task.creator_id == user.id, Task.task_type == OPEN_TASK_TYPE)
        .order_by(Task.deadline)
    )
    result: list[OpenTaskWithApplications] = []
    for task in tasks.all():
        participants = await session.scalars(
            select(TaskParticipant).where(TaskParticipant.task_id == task.id)
        )
        applications: list[OpenTaskApplication] = []
        for participant in participants.all():
            applicant = await session.get(User, participant.user_id)
            if applicant is None:
                continue
            applications.append(OpenTaskApplication(participant=participant, applicant=applicant))
        result.append(OpenTaskWithApplications(task=task, applications=applications))
    return result


async def decide_task_application(
    session: AsyncSession,
    *,
    task: Task,
    target: User,
    action: str,
    actor: User,
    bot: Bot | None,
) -> TaskParticipant:
    if action not in ("accept", "reject"):
        raise ValueError("unknown_action")
    if task.creator_id != actor.id:
        raise PermissionError("not_task_owner")
    participant = await session.scalar(
        select(TaskParticipant).where(
            TaskParticipant.task_id == task.id, TaskParticipant.user_id == target.id
        )
    )
    if participant is None:
        raise ValueError("application_not_found")
    if action == "accept":
        accepted = await session.scalars(
            select(TaskParticipant).where(
                TaskParticipant.task_id == task.id,
                TaskParticipant.status.in_(["accepted", "joined"]),
            )
        )
        if task.max_participants and len(accepted.all()) >= task.max_participants:
            raise ValueError("capacity_reached")
        participant.status = "accepted"
        if bot is not None:
            await safe_send(
                bot,
                target.telegram_id,
                "Вас приняли в открытую задачу ЭРА.\n\n"
                f"{task.title}\n\nОткройте Личный кабинет → Мои задачи и отправьте результат "
                "после выполнения.",
            )
    else:
        participant.status = "rejected"
        if bot is not None:
            await safe_send(
                bot,
                target.telegram_id,
                "Заявка на открытую задачу не была принята.\n\n"
                f"{task.title}\n\nБудут новые возможности — выбирайте следующую задачу в "
                "личном кабинете.",
            )
    await audit(
        session,
        actor_id=actor.id,
        action=f"task.application_{action}",
        entity_type="task",
        entity_id=task.id,
        new_value={"user_id": target.id},
    )
    return participant
