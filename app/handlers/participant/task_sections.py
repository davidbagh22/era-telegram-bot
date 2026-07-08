from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Task, TaskParticipant, User
from app.keyboards.participant import tasks_keyboard
from app.utils import texts
from app.utils.constants import ApplicationStatus, TASK_STATUS_LABELS

router = Router(name="task_sections")


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return False
    if user.is_blocked or user.is_archived:
        await call.message.answer(texts.BLOCKED)
        return False
    return True


async def _tasks_for_user(session: AsyncSession, user: User) -> tuple[list[Task], set[int]]:
    tasks = (
        await session.scalars(
            select(Task)
            .where(
                or_(
                    Task.assignee_id == user.id,
                    Task.status == "published",
                    Task.task_type == "challenge",
                )
            )
            .order_by(Task.deadline)
        )
    ).all()
    tasks = [
        task
        for task in tasks
        if task.assignee_id == user.id
        or not (task.audience_filter_json or {}).get("role")
        or (task.audience_filter_json or {}).get("role") == user.role
    ]
    participants = (
        await session.scalars(
            select(TaskParticipant).where(
                TaskParticipant.user_id == user.id,
                TaskParticipant.task_id.in_([task.id for task in tasks] or [-1]),
            )
        )
    ).all()
    joined_ids = {item.task_id for item in participants}
    joined_ids.update(task.id for task in tasks if task.assignee_id == user.id)
    return tasks, joined_ids


def _body(title: str, tasks: list[Task]) -> str:
    if not tasks:
        return f"{title}\n\nЗдесь пока пусто."
    lines = []
    for task in tasks:
        deadline = f"до {task.deadline:%d.%m.%Y}" if task.deadline else "без срока"
        lines.append(
            f"• {task.title} — {TASK_STATUS_LABELS.get(task.status, 'Открыто')}, {deadline} · {task.points} баллов"
        )
    return f"{title}\n\n" + "\n".join(lines)


@router.callback_query(F.data.regexp(r"^cabinet:tasks:(available|active|archive)$"))
async def task_section(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if not await _guard(call, user):
        return
    tasks, joined_ids = await _tasks_for_user(session, user)
    if call.data == "cabinet:tasks:available":
        filtered = [task for task in tasks if task.id not in joined_ids and task.status in {"published", "new"}]
        title = "📌 Задачи для выполнения"
    elif call.data == "cabinet:tasks:active":
        filtered = [task for task in tasks if task.id in joined_ids and task.status in {"new", "published", "in_progress", "review"}]
        title = "⏳ Задачи в работе"
    else:
        filtered = [task for task in tasks if task.id in joined_ids and task.status in {"completed", "overdue", "cancelled"}]
        title = "📁 Архив задач"
    await call.message.answer(_body(title, filtered), reply_markup=tasks_keyboard(filtered, joined_ids))
