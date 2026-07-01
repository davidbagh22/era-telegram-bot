from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Task, TaskParticipant, TaskSubmission, User
from app.services.notification_service import notify_admins
from app.states.growth import TaskSubmissionStates
from app.utils import texts
from app.utils.constants import ApplicationStatus
from app.utils.validators import clean_text

router = Router(name="participant_task_review_addon")


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


async def _can_submit_task(session: AsyncSession, task: Task, user: User) -> bool:
    if task.assignee_id == user.id:
        return True
    membership = await _membership(session, task.id, user.id)
    return bool(membership and membership.status in {"accepted", "joined"})


def _review_keyboard(submission_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Проверить результат",
                    callback_data=f"admin:tasksub:view:{submission_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Одобрить и начислить баллы",
                    callback_data=f"admin:tasksub:approve:{submission_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Написать / доработка",
                    callback_data=f"admin:tasksub:comment:{submission_id}",
                )
            ],
        ]
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
        "После отправки админ сможет обсудить результат, вернуть на доработку или одобрить и начислить баллы."
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
    submission = TaskSubmission(
        task_id=task.id,
        user_id=user.id,
        text=text_value,
        file_id=file_id,
        status="pending",
    )
    session.add(submission)
    task.status = "review"
    await session.flush()
    await state.clear()
    await message.answer("Результат отправлен. После проверки Вы получите уведомление и награду")
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    await notify_admins(
        bot,
        settings,
        f"📥 Новый результат задания\n\n{task.title}\n"
        f"Участник: {user.first_name} {user.last_name or ''}\n"
        f"Telegram: {telegram}\n"
        f"Баллы после одобрения: {task.points}",
        reply_markup=_review_keyboard(submission.id),
    )
