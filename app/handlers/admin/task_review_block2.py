from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import PointTransaction, Task, TaskSubmission, User
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.utils import texts
from app.utils.constants import Role, TaskStatus

router = Router(name="admin_task_review_block2")


class TaskReviewStates(StatesGroup):
    revision_comment = State()
    reject_comment = State()


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (user and not user.is_blocked and any(grant.is_active for grant in (user.permission_grants or [])))
    )


async def _guard(event: CallbackQuery | Message, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    if not _is_admin(user, settings, telegram_id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def _review_keyboard(submission_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить и начислить баллы", callback_data=f"admin:tasksub:approve:{submission_id}")],
            [InlineKeyboardButton(text="💬 Вернуть на доработку", callback_data=f"admin:tasksub:revision:{submission_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:tasksub:reject:{submission_id}")],
        ]
    )


def _task_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 Результаты на проверке", callback_data="admin:task_submissions")],
            [InlineKeyboardButton(text="← События", callback_data="admin:menu:activity")],
        ]
    )


async def _context(session: AsyncSession, submission_id: int) -> tuple[TaskSubmission | None, Task | None, User | None]:
    submission = await session.get(TaskSubmission, submission_id)
    if not submission:
        return None, None, None
    task = await session.get(Task, submission.task_id)
    participant = await session.get(User, submission.user_id)
    return submission, task, participant


async def _already_awarded(session: AsyncSession, user_id: int, task_id: int) -> bool:
    previous = await session.scalar(
        select(PointTransaction).where(
            PointTransaction.user_id == user_id,
            PointTransaction.related_task_id == task_id,
            PointTransaction.points > 0,
        )
    )
    return previous is not None


async def _send_submission_card(message: Message, session: AsyncSession, submission_id: int) -> None:
    submission, task, participant = await _context(session, submission_id)
    if not submission or not task or not participant:
        await message.answer("Результат не найден")
        return
    telegram = f"@{participant.username}" if participant.username else str(participant.telegram_id)
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
        f"Telegram: {telegram}\n"
        f"Телефон: {participant.phone or 'не указан'}\n"
        f"Email: {participant.email or 'не указан'}\n\n"
        f"Статус: {status}\n"
        f"Баллы за задание: {task.points}\n\n"
        f"Итог участника:\n{submission.text or 'текст не прикреплён'}",
        reply_markup=_review_keyboard(submission.id),
    )
    if submission.file_id:
        try:
            await message.answer_photo(submission.file_id, caption="Файл результата")
        except Exception:
            await message.answer_document(submission.file_id, caption="Файл результата")


@router.callback_query(F.data == "admin:tasks")
async def tasks_menu(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer("✅ Задания\n\nПроверка результатов, доработки и начисление баллов.", reply_markup=_task_menu())


@router.callback_query(F.data == "admin:task_submissions")
async def task_submissions(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    submissions = (
        await session.scalars(
            select(TaskSubmission)
            .where(TaskSubmission.status == "pending")
            .order_by(TaskSubmission.created_at.desc())
            .limit(30)
        )
    ).all()
    if not submissions:
        await call.message.answer("Результатов заданий на проверке пока нет.", reply_markup=_task_menu())
        return
    await call.message.answer(f"Результаты на проверке: {len(submissions)}")
    for submission in submissions:
        await _send_submission_card(call.message, session, submission.id)


@router.callback_query(F.data.startswith("admin:tasksub:approve:"))
async def approve_submission(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(call, user, settings):
        return
    submission, task, participant = await _context(session, int(call.data.rsplit(":", 1)[-1]))
    if not submission or not task or not participant:
        await call.message.answer("Результат не найден")
        return
    if submission.status == "approved":
        await call.message.answer("Этот результат уже одобрен. Повторно баллы не начисляются.")
        return
    submission.status = "approved"
    submission.reviewed_by = user.id if user else None
    task.status = TaskStatus.COMPLETED
    if await _already_awarded(session, participant.id, task.id):
        await call.message.answer("Результат принят. Баллы за это задание уже начислялись ранее.")
        return
    await add_points(
        session,
        user_id=participant.id,
        points=task.points,
        reason=f"Выполнение задания: {task.title}",
        approved_by=user.id if user else None,
        related_task_id=task.id,
    )
    await safe_send(bot, participant.telegram_id, f"Ваш результат по заданию одобрен.\n\n{task.title}\n\nНачислено: {task.points} баллов")
    await call.message.answer("Результат одобрен. Баллы начислены один раз.")


@router.callback_query(F.data.startswith("admin:tasksub:revision:"))
async def revision_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(TaskReviewStates.revision_comment)
    await state.update_data(task_submission_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer("Напишите комментарий участнику: что исправить или дополнить.")


@router.message(TaskReviewStates.revision_comment)
async def revision_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    submission, task, participant = await _context(session, int(data["task_submission_id"]))
    if not submission or not task or not participant:
        await state.clear()
        await message.answer("Результат не найден")
        return
    comment = (message.text or "").strip()[:2000]
    if not comment:
        await message.answer("Комментарий обязателен")
        return
    submission.status = "needs_revision"
    submission.admin_comment = comment
    submission.reviewed_by = user.id if user else None
    task.status = TaskStatus.IN_PROGRESS
    await safe_send(bot, participant.telegram_id, f"Комментарий по заданию:\n\n{task.title}\n\n{comment}\n\nДоработайте результат и отправьте его повторно через Личный кабинет → Мои задачи.")
    await state.clear()
    await message.answer("Комментарий отправлен. Задание возвращено на доработку.")


@router.callback_query(F.data.startswith("admin:tasksub:reject:"))
async def reject_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(TaskReviewStates.reject_comment)
    await state.update_data(task_submission_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer("Напишите причину отклонения результата.")


@router.message(TaskReviewStates.reject_comment)
async def reject_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    submission, task, participant = await _context(session, int(data["task_submission_id"]))
    if not submission or not task or not participant:
        await state.clear()
        await message.answer("Результат не найден")
        return
    comment = (message.text or "").strip()[:2000]
    if not comment:
        await message.answer("Причина обязательна")
        return
    submission.status = "rejected"
    submission.admin_comment = comment
    submission.reviewed_by = user.id if user else None
    await safe_send(bot, participant.telegram_id, f"Результат по заданию не принят.\n\n{task.title}\n\nПричина: {comment}\n\nБаллы не начислены.")
    await state.clear()
    await message.answer("Результат отклонён. Баллы не начислены.")
