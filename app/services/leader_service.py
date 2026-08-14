from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    Event,
    Project,
    Task,
    TaskDelivery,
    TaskParticipant,
    User,
    UserDepartment,
    UserDirection,
)
from app.keyboards.participant import open_app_button
from app.services.audit_service import audit
from app.services.notification_service import safe_send
from app.utils.constants import ApplicationStatus, Role
from app.utils.deep_links import miniapp_task_url

OPEN_TASK_TYPE = "challenge"

# The 4 org chats a task announcement can be dispatched to (2026-08 master
# spec section 31) -- same 4 keys as chat_access_service.CHAT_SETTING_KEYS,
# duplicated here as a plain tuple rather than importing that dict to avoid
# a service->service import for 4 literal strings.
CHAT_DESTINATION_KEYS = ("general", "internal", "external", "leaders")


def _destination_chat_id(settings: Settings, chat_key: str) -> int | None:
    return {
        "general": settings.general_chat_id,
        "internal": settings.internal_department_chat_id,
        "external": settings.external_department_chat_id,
        "leaders": settings.leaders_chat_id,
    }.get(chat_key)


async def dispatch_task_to_chats(
    session: AsyncSession,
    bot: Bot | None,
    settings: Settings,
    task: Task,
    destinations: list[str],
    *,
    miniapp_url: str = "",
) -> list[TaskDelivery]:
    """Announces a task in each requested chat and records one TaskDelivery
    row per destination, success or failure -- never raises, since task
    creation itself must succeed regardless of whether Telegram delivery
    does (2026-08 master spec section 32: "создано, но не доставлено", not
    a rolled-back task). Unbound/unknown chat keys are recorded as an
    immediate failure (no chat_id to send to) rather than silently skipped,
    so they show up in the same "not delivered" list an admin/leader
    reviews, with a real reason instead of nothing."""
    deliveries: list[TaskDelivery] = []
    keyboard = open_app_button(miniapp_task_url(miniapp_url, task.id)) if miniapp_url else None
    text = f"📌 Новое задание ЭРА\n\n{task.title}\n{task.description}\n\nБаллы: {task.points}"
    for chat_key in destinations:
        chat_id = _destination_chat_id(settings, chat_key)
        if chat_id is None:
            delivery = TaskDelivery(task_id=task.id, chat_key=chat_key, chat_id=0, status="failed", error="chat_not_bound")
            session.add(delivery)
            deliveries.append(delivery)
            continue
        delivery = await _send_and_record(session, bot, chat_id, chat_key, task.id, text, keyboard)
        deliveries.append(delivery)
    await session.flush()
    return deliveries


async def _send_and_record(
    session: AsyncSession,
    bot: Bot | None,
    chat_id: int,
    chat_key: str,
    task_id: int,
    text: str,
    keyboard: InlineKeyboardMarkup | None,
) -> TaskDelivery:
    if bot is None:
        delivery = TaskDelivery(task_id=task_id, chat_key=chat_key, chat_id=chat_id, status="failed", error="bot_unavailable")
        session.add(delivery)
        return delivery
    try:
        message = await bot.send_message(chat_id, text, reply_markup=keyboard)
        delivery = TaskDelivery(
            task_id=task_id,
            chat_key=chat_key,
            chat_id=chat_id,
            telegram_message_id=message.message_id,
            status="sent",
            sent_at=datetime.now().astimezone(),
        )
    except TelegramAPIError as exc:
        delivery = TaskDelivery(task_id=task_id, chat_key=chat_key, chat_id=chat_id, status="failed", error=str(exc)[:500])
    session.add(delivery)
    return delivery


async def retry_task_delivery(
    session: AsyncSession, bot: Bot | None, delivery: TaskDelivery, task: Task, *, keyboard: InlineKeyboardMarkup | None = None
) -> TaskDelivery:
    """Re-attempts exactly one failed destination -- not the whole task,
    since the other destinations may already have succeeded and resending
    to them would just duplicate the announcement."""
    text = f"📌 Новое задание ЭРА\n\n{task.title}\n{task.description}\n\nБаллы: {task.points}"
    updated = await _send_and_record(session, bot, delivery.chat_id, delivery.chat_key, task.id, text, keyboard)
    await session.flush()
    return updated


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
    miniapp_url: str = "",
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
        # task.id only exists after the flush above, so the deep link is
        # built here rather than by the caller (see app/api/v1/leader.py).
        keyboard = open_app_button(miniapp_task_url(miniapp_url, task.id)) if miniapp_url else None
        await safe_send(
            bot,
            assignee.telegram_id,
            f"У Вас новая задача ЭРА.\n\n{task.title}\n{task.description}\n\n"
            f"Дедлайн: {task.deadline:%d.%m.%Y %H:%M}",
            keyboard,
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
    destinations: list[str] | None = None,
    bot: Bot | None = None,
    settings: Settings | None = None,
    miniapp_url: str = "",
) -> Task:
    # destinations/bot/settings/miniapp_url are all optional and default to
    # "dispatch nothing" -- existing callers (the bot-native
    # app/handlers/leader/open_tasks.py flow, which has no chat-selection
    # UI) are unaffected; this keeps create_open_task()'s return type as
    # just Task rather than breaking every existing caller's unpacking.
    # Deliveries are read back afterwards via list_task_deliveries(),
    # not returned here.
    if not 0 <= points <= 1000:
        raise ValueError("invalid_points")
    if not 1 <= max_participants <= 50:
        raise ValueError("invalid_max_participants")
    unknown = set(destinations or []) - set(CHAT_DESTINATION_KEYS)
    if unknown:
        raise ValueError("invalid_destination")
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
    # Task creation itself is already committed to the session above
    # regardless of what happens next -- dispatch_task_to_chats() never
    # raises, so a Telegram outage can never roll this back (2026-08
    # master spec section 32).
    if destinations and settings is not None:
        await dispatch_task_to_chats(session, bot, settings, task, destinations, miniapp_url=miniapp_url)
    return task


async def list_task_deliveries(session: AsyncSession, task_id: int) -> list[TaskDelivery]:
    """Most-recent attempt per chat_key -- a retried delivery adds a new
    row (audit-trail style, consistent with AuditLog elsewhere in this
    app) rather than overwriting the failed one, so this reads the latest
    per destination rather than every row ever recorded. Ordered by id,
    not created_at -- a retry immediately after the original attempt can
    land in the same server_default=func.now() second, and id is the one
    monotonic, insertion-order-reliable tiebreaker SQLite and Postgres
    both actually guarantee."""
    rows = (
        await session.scalars(
            select(TaskDelivery).where(TaskDelivery.task_id == task_id).order_by(TaskDelivery.id.desc())
        )
    ).all()
    latest: dict[str, TaskDelivery] = {}
    for row in rows:
        latest.setdefault(row.chat_key, row)
    return list(latest.values())


@dataclass(frozen=True)
class OpenTaskApplication:
    participant: TaskParticipant
    applicant: User


@dataclass(frozen=True)
class OpenTaskWithApplications:
    task: Task
    applications: list[OpenTaskApplication]
    deliveries: list[TaskDelivery] = field(default_factory=list)


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
        deliveries = await list_task_deliveries(session, task.id)
        result.append(OpenTaskWithApplications(task=task, applications=applications, deliveries=deliveries))
    return result


async def decide_task_application(
    session: AsyncSession,
    *,
    task: Task,
    target: User,
    action: str,
    actor: User,
    bot: Bot | None,
    keyboard: InlineKeyboardMarkup | None = None,
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
                keyboard,
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
