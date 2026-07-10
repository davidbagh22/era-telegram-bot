from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Task, TaskParticipant, TaskSubmission, User
from app.keyboards.participant import tasks_keyboard
from app.services.notification_service import notify_admins
from app.states.growth import TaskSubmissionStates
from app.utils import texts, ux_texts
from app.utils.constants import ApplicationStatus, TASK_STATUS_LABELS
from app.utils.validators import clean_text

router = Router(name="participant_task_block2")
ARCHIVE_STATUSES = {"completed", "cancelled", "rejected"}


def _approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


def _task_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Задачи в работе", callback_data="tasks:list:active")],
        [InlineKeyboardButton(text="🗂 Архив задач", callback_data="tasks:list:archive")],
        [InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")],
    ])


def _review_keyboard(submission_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить и начислить баллы", callback_data=f"admin:tasksub:approve:{submission_id}")],
        [InlineKeyboardButton(text="💬 Вернуть на доработку", callback_data=f"admin:tasksub:revision:{submission_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:tasksub:reject:{submission_id}")],
    ])


async def _membership(session: AsyncSession, task_id: int, user_id: int) -> TaskParticipant | None:
    return await session.scalar(select(TaskParticipant).where(TaskParticipant.task_id == task_id, TaskParticipant.user_id == user_id))


async def _can_view(session: AsyncSession, task: Task, user: User) -> bool:
    if task.assignee_id == user.id:
        return True
    item = await _membership(session, task.id, user.id)
    if item and item.status in {"pending", "accepted", "joined"}:
        return True
    return task.task_type == "challenge" and task.status == "published"


async def _can_submit(session: AsyncSession, task: Task, user: User) -> bool:
    if task.assignee_id == user.id:
        return True
    item = await _membership(session, task.id, user.id)
    return bool(item and item.status in {"accepted", "joined"})


async def _tasks_for_user(session: AsyncSession, user: User) -> list[Task]:
    direct_tasks = (await session.scalars(
        select(Task).where(or_(Task.assignee_id == user.id, ((Task.task_type == "challenge") & (Task.status == "published"))))
    )).all()
    memberships = (await session.scalars(select(TaskParticipant).where(TaskParticipant.user_id == user.id))).all()
    tasks_by_id = {task.id: task for task in direct_tasks}
    for membership in memberships:
        task = await session.get(Task, membership.task_id)
        if task and membership.status in {"pending", "accepted", "joined"}:
            tasks_by_id[task.id] = task
    tasks = sorted(tasks_by_id.values(), key=lambda item: item.deadline)
    return [
        task for task in tasks
        if task.assignee_id == user.id
        or task.id in {membership.task_id for membership in memberships if membership.status in {"pending", "accepted", "joined"}}
        or not (task.audience_filter_json or {}).get("role")
        or (task.audience_filter_json or {}).get("role") == user.role
    ]


async def _send_task_file(call: CallbackQuery, task: Task) -> None:
    if not task.file_id:
        return
    try:
        await call.message.answer_photo(task.file_id, caption="Материал к заданию")
        return
    except Exception:
        pass
    try:
        await call.message.answer_video(task.file_id, caption="Материал к заданию")
        return
    except Exception:
        pass
    try:
        await call.message.answer_document(task.file_id, caption="Материал к заданию")
    except Exception:
        await call.message.answer("К заданию прикреплён файл, но Telegram не дал открыть его повторно.")


@router.message(F.text == "✅ Задачи")
async def tasks_reply_button(message: Message, user: User | None, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer("✅ Мои задачи\n\nВыберите раздел:", reply_markup=_task_menu())


@router.callback_query(F.data == "cabinet:tasks")
async def tasks_root(call: CallbackQuery, user: User | None) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await call.message.answer(ux_texts.TASKS_MENU, reply_markup=_task_menu())


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
        empty = ux_texts.TASKS_EMPTY_ARCHIVE
    else:
        tasks = [task for task in all_tasks if task.status not in ARCHIVE_STATUSES]
        title = "🟢 Задачи в работе"
        empty = ux_texts.TASKS_EMPTY_ACTIVE
    participants = (await session.scalars(select(TaskParticipant).where(TaskParticipant.user_id == user.id, TaskParticipant.task_id.in_([task.id for task in tasks] or [-1])))).all()
    joined_ids = {item.task_id for item in participants if item.status in {"pending", "accepted", "joined"}}
    joined_ids.update(task.id for task in tasks if task.assignee_id == user.id)
    body = "\n".join(f"• {task.title} — {TASK_STATUS_LABELS.get(task.status, task.status)}, до {task.deadline:%d.%m.%Y} · {task.points} баллов" for task in tasks) or empty
    await call.message.answer(f"{title}\n\n{body}", reply_markup=tasks_keyboard(tasks, joined_ids) if tasks else _task_menu())


@router.callback_query(F.data.startswith("task:view:"))
async def task_view(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        return
    task = await session.get(Task, int(call.data.rsplit(":", 1)[-1]))
    if task is None or not await _can_view(session, task, user):
        await call.message.answer(texts.NO_ACCESS)
        return
    membership = await _membership(session, task.id, user.id)
    rows = []
    if await _can_submit(session, task, user) and task.status not in ARCHIVE_STATUSES:
        rows.append([InlineKeyboardButton(text="📤 Отправить результат", callback_data=f"task:result:{task.id}")])
    elif membership and membership.status == "pending":
        rows.append([InlineKeyboardButton(text="⏳ Заявка на рассмотрении", callback_data="cabinet:tasks")])
    elif task.task_type == "challenge" and task.status == "published":
        rows.append([InlineKeyboardButton(text="🙌 Хочу помочь", callback_data=f"task:join:{task.id}")])
    if task.chat_url and await _can_submit(session, task, user):
        rows.append([InlineKeyboardButton(text="💬 Чат команды", url=task.chat_url)])
    rows.append([InlineKeyboardButton(text="← Мои задачи", callback_data="cabinet:tasks")])
    await call.message.answer(
        f"✅ {task.title}\n\n{task.description}\n\nСрок: {task.deadline:%d.%m.%Y %H:%M}\nНаграда: {task.points} баллов\nСтатус: {TASK_STATUS_LABELS.get(task.status, task.status)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await _send_task_file(call, task)


@router.callback_query(F.data.startswith("task:result:"))
async def task_result_start(call: CallbackQuery, user: User | None, state: FSMContext, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        return
    task = await session.get(Task, int(call.data.rsplit(":", 1)[-1]))
    if task is None or task.status in ARCHIVE_STATUSES or not await _can_submit(session, task, user):
        await call.message.answer(texts.NO_ACCESS)
        return
    await state.set_state(TaskSubmissionStates.result)
    await state.update_data(task_id=task.id)
    await call.message.answer("Отправьте результат текстом, фотографией, видео или файлом\n\nАдмин сможет принять, вернуть на доработку или отклонить результат.")


@router.message(TaskSubmissionStates.result)
async def task_result_save(message: Message, user: User, session: AsyncSession, state: FSMContext, bot: Bot, settings: Settings) -> None:
    data = await state.get_data()
    task = await session.get(Task, int(data["task_id"]))
    if task is None or not await _can_submit(session, task, user):
        await state.clear()
        await message.answer(texts.NO_ACCESS)
        return
    text_value = clean_text(message.text or message.caption or "", 3000) or None
    file_id = None
    file_type = None
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    if not text_value and not file_id:
        await message.answer("Добавьте текст или прикрепите материал")
        return
    submission = TaskSubmission(task_id=task.id, user_id=user.id, text=text_value, file_id=file_id, status="pending")
    session.add(submission)
    task.status = "review"
    await session.flush()
    await state.clear()
    await message.answer("Результат отправлен на проверку. После решения админа Вы получите уведомление.")
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    await notify_admins(bot, settings, f"📥 Новый результат задания\n\n{task.title}\nУчастник: {user.first_name} {user.last_name or ''}\nTelegram: {telegram}\n\n{submission.text or 'Материал прикреплён файлом'}", reply_markup=_review_keyboard(submission.id))
    if file_id:
        for chat_id in set(settings.admin_ids):
            try:
                if file_type == "photo":
                    await bot.send_photo(chat_id, file_id, caption="Файл результата")
                elif file_type == "video":
                    await bot.send_video(chat_id, file_id, caption="Файл результата")
                else:
                    await bot.send_document(chat_id, file_id, caption="Файл результата")
            except Exception:
                pass
