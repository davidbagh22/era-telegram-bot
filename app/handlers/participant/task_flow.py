from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Task, TaskParticipant, TaskSubmission, User
from app.keyboards.common import back_keyboard
from app.keyboards.participant import tasks_keyboard
from app.services.notification_service import notify_admins
from app.states.growth import TaskSubmissionStates
from app.utils import texts
from app.utils.constants import ApplicationStatus, TASK_STATUS_LABELS
from app.utils.validators import clean_text

router = Router(name="participant_task_flow")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


async def _membership(session: AsyncSession, task_id: int, user_id: int) -> TaskParticipant | None:
    return await session.scalar(
        select(TaskParticipant).where(
            TaskParticipant.task_id == task_id,
            TaskParticipant.user_id == user_id,
        )
    )


async def _can_view_task(session: AsyncSession, task: Task, user: User) -> bool:
    if task.assignee_id == user.id:
        return True
    membership = await _membership(session, task.id, user.id)
    if membership and membership.status in {"pending", "accepted", "joined"}:
        return True
    return task.task_type == "challenge" and task.status == "published"


async def _can_submit_task(session: AsyncSession, task: Task, user: User) -> bool:
    if task.assignee_id == user.id:
        return True
    membership = await _membership(session, task.id, user.id)
    return bool(membership and membership.status in {"accepted", "joined"})


@router.callback_query(F.data == "cabinet:tasks")
async def my_tasks(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    tasks = (
        await session.scalars(
            select(Task)
            .where(
                or_(
                    Task.assignee_id == user.id,
                    ((Task.task_type == "challenge") & (Task.status == "published")),
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
    joined_ids = {
        item.task_id
        for item in participants
        if item.status in {"pending", "accepted", "joined"}
    }
    joined_ids.update(task.id for task in tasks if task.assignee_id == user.id)
    body = (
        "\n".join(
            f"• {task.title} — {TASK_STATUS_LABELS.get(task.status, 'Открыто')}, "
            f"до {task.deadline:%d.%m.%Y} · {task.points} баллов"
            for task in tasks
        )
        or "Задач пока нет."
    )
    await call.message.answer(body, reply_markup=tasks_keyboard(tasks, joined_ids))


@router.callback_query(F.data.startswith("task:join:"))
async def task_join(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        return
    task = await session.get(Task, int(call.data.rsplit(":", 1)[-1]))
    if task is None or task.task_type != "challenge" or task.status != "published":
        await call.message.answer("Набор на это задание уже закрыт")
        return
    current = (
        await session.scalars(
            select(TaskParticipant).where(TaskParticipant.task_id == task.id)
        )
    ).all()
    accepted = [item for item in current if item.status in {"accepted", "joined"}]
    if task.max_participants and len(accepted) >= task.max_participants:
        await call.message.answer("Команда уже набрана")
        return
    existing = next((item for item in current if item.user_id == user.id), None)
    if existing:
        if existing.status == "rejected":
            existing.status = "pending"
        elif existing.status == "pending":
            await call.message.answer("Ваша заявка уже у лидера на рассмотрении.", reply_markup=back_keyboard("cabinet:tasks"))
            return
        else:
            await call.message.answer("Вы уже в команде этой задачи.", reply_markup=back_keyboard("cabinet:tasks"))
            return
    else:
        session.add(TaskParticipant(task_id=task.id, user_id=user.id, status="pending"))
    await call.message.answer(
        "Заявка отправлена лидеру 🙌\n\nЕсли лидер примет Вас в команду, задача появится как активная в личном кабинете.",
        reply_markup=back_keyboard("cabinet:tasks"),
    )


@router.callback_query(F.data.startswith("task:view:"))
async def task_view(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        return
    task = await session.get(Task, int(call.data.rsplit(":", 1)[-1]))
    if task is None or not await _can_view_task(session, task, user):
        await call.message.answer(texts.NO_ACCESS)
        return
    membership = await _membership(session, task.id, user.id)
    memberships = (
        await session.scalars(select(TaskParticipant).where(TaskParticipant.task_id == task.id))
    ).all()
    members = []
    for item in memberships:
        if item.status not in {"accepted", "joined"}:
            continue
        person = await session.get(User, item.user_id)
        if person:
            members.append(f"@{person.username}" if person.username else person.first_name)
    rows = []
    if await _can_submit_task(session, task, user):
        rows.append([InlineKeyboardButton(text="📤 Отправить результат", callback_data=f"task:result:{task.id}")])
    elif membership and membership.status == "pending":
        rows.append([InlineKeyboardButton(text="⏳ Заявка на рассмотрении", callback_data="cabinet:tasks")])
    elif task.task_type == "challenge" and task.status == "published":
        rows.append([InlineKeyboardButton(text="🙌 Хочу помочь", callback_data=f"task:join:{task.id}")])
    if task.chat_url and await _can_submit_task(session, task, user):
        rows.append([InlineKeyboardButton(text="💬 Чат команды", url=task.chat_url)])
    rows.append([InlineKeyboardButton(text="← Мои задачи", callback_data="cabinet:tasks")])
    await call.message.answer(
        f"✅ {task.title}\n\n{task.description}\n\n"
        f"Срок: {task.deadline:%d.%m.%Y %H:%M}\n"
        f"Награда: {task.points} баллов\n\n"
        f"Команда: {', '.join(members) or 'пока формируется'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("task:result:"))
async def task_result_start(
    call: CallbackQuery,
    user: User | None,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await call.answer()
    if not _approved(user):
        return
    task = await session.get(Task, int(call.data.rsplit(":", 1)[-1]))
    if task is None or not await _can_submit_task(session, task, user):
        await call.message.answer(texts.NO_ACCESS)
        return
    await state.set_state(TaskSubmissionStates.result)
    await state.update_data(task_id=task.id)
    await call.message.answer(
        "Отправьте результат текстом, фотографией, видео или файлом\n\n"
        "Укажите, с кем Вы работали и что получилось"
    )


@router.message(TaskSubmissionStates.result)
async def task_result_save(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
) -> None:
    data = await state.get_data()
    task = await session.get(Task, int(data["task_id"]))
    if task is None or not await _can_submit_task(session, task, user):
        await state.clear()
        await message.answer(texts.NO_ACCESS)
        return
    text_value = clean_text(message.text or message.caption or "", 3000) or None
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.video:
        file_id = message.video.file_id
    elif message.document:
        file_id = message.document.file_id
    if not text_value and not file_id:
        await message.answer("Добавьте текст или прикрепите материал")
        return
    session.add(
        TaskSubmission(
            task_id=task.id,
            user_id=user.id,
            text=text_value,
            file_id=file_id,
            status="pending",
        )
    )
    await state.clear()
    await message.answer("Результат отправлен. После проверки Вы получите уведомление и награду")
    await notify_admins(
        bot,
        settings,
        f"✅ Новый результат задания\n\n{task.title}\n"
        f"Участник: {user.first_name} {user.last_name or ''}",
    )
