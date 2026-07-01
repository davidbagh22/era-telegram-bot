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


def _approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


def _task_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Задачи в работе", callback_data="tasks:list:active")],
        [InlineKeyboardButton(text="🗂 Архив задач", callback_data="tasks:list:archive")],
        [InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")],
    ])


async def _membership(session: AsyncSession, task_id: int, user_id: int):
    return await session.scalar(select(TaskParticipant).where(TaskParticipant.task_id == task_id, TaskParticipant.user_id == user_id))


async def _tasks_for_user(session: AsyncSession, user: User) -> list[Task]:
    rows = (await session.scalars(select(Task).where(or_(Task.assignee_id == user.id, ((Task.task_type == "challenge") & (Task.status == "published")))).order_by(Task.deadline))).all()
    return [t for t in rows if t.assignee_id == user.id or not (t.audience_filter_json or {}).get("role") or (t.audience_filter_json or {}).get("role") == user.role]


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
    tasks = [t for t in all_tasks if (t.status in ARCHIVE_STATUSES) == (mode == "archive")]
    title = "🗂 Архив задач" if mode == "archive" else "🟢 Задачи в работе"
    links = (await session.scalars(select(TaskParticipant).where(TaskParticipant.user_id == user.id, TaskParticipant.task_id.in_([t.id for t in tasks] or [-1])))).all()
    joined = {x.task_id for x in links if x.status in {"pending", "accepted", "joined"}} | {t.id for t in tasks if t.assignee_id == user.id}
    body = "\n".join(f"• {t.title} — {TASK_STATUS_LABELS.get(t.status, 'Открыто')}, до {t.deadline:%d.%m.%Y} · {t.points} баллов" for t in tasks) or "Здесь пока пусто."
    await call.message.answer(f"{title}\n\n{body}", reply_markup=tasks_keyboard(tasks, joined) if tasks else _task_menu())


@router.callback_query(F.data.startswith("task:view:"))
async def task_view_card(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    task = await session.get(Task, int(call.data.rsplit(":", 1)[-1]))
    if not task:
        await call.message.answer(texts.NO_ACCESS)
        return
    link = await _membership(session, task.id, user.id)
    can_view = task.assignee_id == user.id or (link and link.status in {"pending", "accepted", "joined"}) or (task.task_type == "challenge" and task.status == "published")
    if not can_view:
        await call.message.answer(texts.NO_ACCESS)
        return
    can_submit = task.assignee_id == user.id or (link and link.status in {"accepted", "joined"})
    rows = []
    if can_submit:
        rows.append([InlineKeyboardButton(text="📤 Отправить результат", callback_data=f"task:result:{task.id}")])
    elif link and link.status == "pending":
        rows.append([InlineKeyboardButton(text="⏳ Заявка на рассмотрении", callback_data="cabinet:tasks")])
    elif task.task_type == "challenge" and task.status == "published":
        rows.append([InlineKeyboardButton(text="🙌 Хочу помочь", callback_data=f"task:join:{task.id}")])
    rows.append([InlineKeyboardButton(text="← Мои задачи", callback_data="cabinet:tasks")])
    await call.message.answer(f"✅ {task.title}\n\n{task.description}\n\nСрок: {task.deadline:%d.%m.%Y %H:%M}\nНаграда: {task.points} баллов", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    if task.file_id:
        try:
            await call.message.answer_photo(task.file_id, caption="Материал к заданию")
        except Exception:
            await call.message.answer_document(task.file_id, caption="Материал к заданию")
