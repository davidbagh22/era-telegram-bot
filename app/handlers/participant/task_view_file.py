from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Task, TaskParticipant, User
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="participant_task_view_file")


def approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


async def membership(session: AsyncSession, task_id: int, user_id: int) -> TaskParticipant | None:
    return await session.scalar(select(TaskParticipant).where(TaskParticipant.task_id == task_id, TaskParticipant.user_id == user_id))


async def can_view(session: AsyncSession, task: Task, user: User) -> bool:
    if task.assignee_id == user.id:
        return True
    item = await membership(session, task.id, user.id)
    if item and item.status in {"pending", "accepted", "joined"}:
        return True
    return task.task_type == "challenge" and task.status == "published"


async def can_submit(session: AsyncSession, task: Task, user: User) -> bool:
    if task.assignee_id == user.id:
        return True
    item = await membership(session, task.id, user.id)
    return bool(item and item.status in {"accepted", "joined"})


@router.callback_query(F.data.startswith("task:view:"))
async def task_view_with_file(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    task = await session.get(Task, int(call.data.rsplit(":", 1)[-1]))
    if task is None or not await can_view(session, task, user):
        await call.message.answer(texts.NO_ACCESS)
        return
    item = await membership(session, task.id, user.id)
    rows = []
    if await can_submit(session, task, user):
        rows.append([InlineKeyboardButton(text="📤 Отправить результат", callback_data=f"task:result:{task.id}")])
    elif item and item.status == "pending":
        rows.append([InlineKeyboardButton(text="⏳ Заявка на рассмотрении", callback_data="cabinet:tasks")])
    elif task.task_type == "challenge" and task.status == "published":
        rows.append([InlineKeyboardButton(text="🙌 Хочу помочь", callback_data=f"task:join:{task.id}")])
    if task.chat_url and await can_submit(session, task, user):
        rows.append([InlineKeyboardButton(text="💬 Чат команды", url=task.chat_url)])
    rows.append([InlineKeyboardButton(text="← Мои задачи", callback_data="cabinet:tasks")])
    await call.message.answer(
        f"✅ {task.title}\n\n{task.description}\n\n"
        f"Срок: {task.deadline:%d.%m.%Y %H:%M}\n"
        f"Награда: {task.points} баллов",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    if task.file_id:
        try:
            await call.message.answer_photo(task.file_id, caption="Материал к заданию")
        except Exception:
            await call.message.answer_document(task.file_id, caption="Материал к заданию")
