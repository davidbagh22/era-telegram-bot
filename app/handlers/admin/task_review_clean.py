from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Task, TaskSubmission, User
from app.utils import texts
from app.utils.constants import Role

router = Router(name="admin_task_review_clean")


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (user and not user.is_blocked and any(g.is_active for g in (user.permission_grants or [])))
    )


async def _guard(call: CallbackQuery, user: User | None, settings: Settings) -> bool:
    await call.answer()
    if not _is_admin(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return False
    return True


def _keyboard(submission_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить и начислить баллы", callback_data=f"admin:tasksub:approve:{submission_id}")],
            [InlineKeyboardButton(text="💬 Написать / вернуть на доработку", callback_data=f"admin:tasksub:comment:{submission_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:tasksub:reject:{submission_id}")],
        ]
    )


def _tg(user: User) -> str:
    return f"@{user.username}" if user.username else str(user.telegram_id)


async def _context(session: AsyncSession, submission_id: int):
    submission = await session.get(TaskSubmission, submission_id)
    if not submission:
        return None, None, None
    task = await session.get(Task, submission.task_id)
    participant = await session.get(User, submission.user_id)
    return submission, task, participant


async def _send_card(message: Message, session: AsyncSession, submission_id: int) -> None:
    submission, task, participant = await _context(session, submission_id)
    if not submission or not task or not participant:
        await message.answer("Результат не найден")
        return
    status = {
        "pending": "на проверке",
        "approved": "одобрено",
        "rejected": "отклонено",
        "needs_revision": "на доработке",
    }.get(submission.status, submission.status)
    await message.answer(
        f"📥 Результат задания #{submission.id}\n\n"
        f"Задание: {task.title}\n"
        f"Участник: {participant.first_name} {participant.last_name or ''}\n"
        f"Telegram: {_tg(participant)}\n"
        f"Телефон: {participant.phone or 'не указан'}\n"
        f"Email: {participant.email or 'не указан'}\n\n"
        f"Статус: {status}\n"
        f"Баллы за задание: {task.points}\n\n"
        f"Итог участника:\n{submission.text or 'без текста'}",
        reply_markup=_keyboard(submission.id),
    )
    if submission.file_id:
        try:
            await message.answer_photo(submission.file_id, caption="Файл результата")
        except Exception:
            await message.answer_document(submission.file_id, caption="Файл результата")


@router.callback_query(F.data == "admin:task_submissions")
async def clean_task_submissions(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    submissions = (
        await session.scalars(
            select(TaskSubmission)
            .where(TaskSubmission.status == "pending")
            .order_by(TaskSubmission.created_at.desc())
            .limit(20)
        )
    ).all()
    if not submissions:
        await call.message.answer("Результатов заданий на проверке пока нет.")
        return
    await call.message.answer(f"Результаты на проверке: {len(submissions)}")
    for submission in submissions:
        await _send_card(call.message, session, submission.id)


@router.callback_query(F.data.startswith("admin:tasksub:view:"))
async def clean_task_submission_view(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    await _send_card(call.message, session, int(call.data.rsplit(":", 1)[-1]))
