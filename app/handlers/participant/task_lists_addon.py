from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Task, TaskParticipant, User
from app.keyboards.participant import tasks_keyboard
from app.utils import texts
from app.utils.constants import ApplicationStatus, TASK_STATUS_LABELS

router = Router(name="participant_task_lists_addon")

ARCHIVE_STATUSES = {"completed", "cancelled", "rejected"}
ACTIVE_STATUSES = {"new", "published", "in_progress", "review", "overdue"}


def _approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


def _task_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Задачи в работе", callback_data="tasks:list:active")],
            [InlineKeyboardButton(text="🗂 Архив задач", callback_data="tasks:list:archive")],
            [InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")],
        ]
    )


async def _tasks_for_user(session: AsyncSession, user: User) -> list[Task]:
    tasks = (
        await session.scalars(
            select(Task)
            .where(or_(Task.assignee_id == user.id, ((Task.task_type == "challenge") & (Task.status == "published"))))
            .order_by(Task.deadline)
        )
    ).all()
    return [
        task
        for task in tasks
        if task.assignee_id == user.id
        or not (task.audience_filter_json or {}).get("role")
        or (task.audience_filter_json or {}).get("role") == user.role
    ]


@router.callback_query(F.data == "cabinet:tasks")
async def tasks_root(call: CallbackQuery, user: User | None) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await call.message.answer("✅ Мои задачи\n\nВыберите, что открыть:", reply_markup=_task_menu())


@router.callback_query(F.data.in_({"tasks:list:active", "tasks:list:archive"}))
async def tasks_list(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    mode = call.data.rsplit(":", 1)[-1]
    all_tasks = await _tasks_for_user(session, user)
    if mode == "archive":
        tasks = [task for task in all_tasks if task.status in ARCHIVE_STATUSES]
        title = "🗂 Архив задач"
    else:
        tasks = [task for task in all_tasks if task.status not in ARCHIVE_STATUSES]
        title = "🟢 Задачи в работе"
    participants = (
        await session.scalars(
            select(TaskParticipant).where(
                TaskParticipant.user_id == user.id,
                TaskParticipant.task_id.in_([task.id for task in tasks] or [-1]),
            )
        )
    ).all()
    joined_ids = {item.task_id for item in participants if item.status in {"pending", "accepted", "joined"}}
    joined_ids.update(task.id for task in tasks if task.assignee_id == user.id)
    body = (
        "\n".join(
            f"• {task.title} — {TASK_STATUS_LABELS.get(task.status, 'Открыто')}, до {task.deadline:%d.%m.%Y} · {task.points} баллов"
            for task in tasks
        )
        or "Здесь пока пусто."
    )
    await call.message.answer(
        f"{title}\n\n{body}",
        reply_markup=tasks_keyboard(tasks, joined_ids) if tasks else _task_menu(),
    )
