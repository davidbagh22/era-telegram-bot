from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Task, TaskSubmission, User
from app.keyboards.admin import admin_panel_keyboard
from app.services.audit_service import audit
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.utils import texts
from app.utils.constants import Role

router = Router(name="admin_task_review")


class AdminTaskReviewStates(StatesGroup):
    comment = State()


def _active_permissions(user: User | None) -> set[str]:
    return {
        grant.permission
        for grant in (getattr(user, "permission_grants", None) or [])
        if grant.is_active
    }


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    if telegram_id in settings.admin_ids:
        return True
    if user and user.role == Role.ADMIN and not user.is_blocked:
        return True
    return bool(user and not user.is_blocked and _active_permissions(user))


async def _guard(event: Message | CallbackQuery, user: User | None, settings: Settings) -> bool:
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


def task_review_keyboard(submission_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить и начислить баллы",
                    callback_data=f"admin:tasksub:approve:{submission_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Написать / вернуть на доработку",
                    callback_data=f"admin:tasksub:comment:{submission_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"admin:tasksub:reject:{submission_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👁 Открыть результат",
                    callback_data=f"admin:tasksub:view:{submission_id}",
                )
            ],
        ]
    )


def task_review_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Дать задание участнику", callback_data="admin:task:new")],
            [InlineKeyboardButton(text="📥 Результаты на проверке", callback_data="admin:task_submissions")],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:menu:activity")],
        ]
    )


def _tg(user: User) -> str:
    return f"@{user.username}" if user.username else str(user.telegram_id)


async def _submission_context(
    session: AsyncSession, submission_id: int
) -> tuple[TaskSubmission | None, Task | None, User | None]:
    submission = await session.get(TaskSubmission, submission_id)
    if not submission:
        return None, None, None
    task = await session.get(Task, submission.task_id)
    participant = await session.get(User, submission.user_id)
    return submission, task, participant


def _submission_text(submission: TaskSubmission, task: Task, participant: User) -> str:
    status = {
        "pending": "на проверке",
        "approved": "одобрено",
        "rejected": "отклонено",
        "needs_revision": "на доработке",
    }.get(submission.status, submission.status)
    return (
        f"📥 Результат задания #{submission.id}\n\n"
        f"Задание: {task.title}\n"
        f"Участник: {participant.first_name} {participant.last_name or ''}\n"
        f"Telegram: {_tg(participant)}\n"
        f"Телефон: {participant.phone or 'не указан'}\n"
        f"Email: {participant.email or 'не указан'}\n\n"
        f"Статус: {status}\n"
        f"Баллы за задание: {task.points}\n\n"
        f"Итог участника:\n{submission.text or 'без текста'}"
    )


async def _send_submission_card(
    message: Message,
    session: AsyncSession,
    submission_id: int,
) -> None:
    submission, task, participant = await _submission_context(session, submission_id)
    if not submission or not task or not participant:
        await message.answer("Результат не найден")
        return
    await message.answer(
        _submission_text(submission, task, participant),
        reply_markup=task_review_keyboard(submission.id),
    )
    if submission.file_id:
        try:
            await message.answer_photo(submission.file_id, caption="Файл результата")
        except Exception:
            try:
                await message.answer_document(submission.file_id, caption="Файл результата")
            except Exception:
                await message.answer("К результату прикреплён файл, но Telegram не дал открыть его повторно.")


@router.callback_query(F.data == "admin:tasks")
async def admin_tasks_menu(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    await call.message.answer(
        "✅ Задания\n\nСоздание, проверка и обсуждение результатов заданий.",
        reply_markup=task_review_menu_keyboard(),
    )


@router.callback_query(F.data == "admin:task_submissions")
async def task_submissions_list(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
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
        await call.message.answer("Результатов заданий на проверке пока нет.", reply_markup=task_review_menu_keyboard())
        return
    await call.message.answer(f"Результаты на проверке: {len(submissions)}")
    for submission in submissions:
        await _send_submission_card(call.message, session, submission.id)


@router.callback_query(F.data.startswith("admin:tasksub:view:"))
async def task_submission_view(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    await _send_submission_card(call.message, session, int(call.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data.startswith("admin:tasksub:approve:"))
async def task_submission_approve(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    submission, task, participant = await _submission_context(
        session, int(call.data.rsplit(":", 1)[-1])
    )
    if not submission or not task or not participant:
        await call.message.answer("Результат не найден")
        return
    if submission.status == "approved":
        await call.message.answer("Этот результат уже одобрен. Баллы повторно не начисляю.")
        return
    submission.status = "approved"
    submission.reviewed_by = user.id if user else None
    task.status = "completed"
    await add_points(
        session,
        user_id=participant.id,
        points=task.points,
        reason=f"Выполнение задания: {task.title}",
        approved_by=user.id if user else None,
        related_task_id=task.id,
    )
    await audit(
        session,
        actor_id=user.id if user else None,
        action="task_submission.approved",
        entity_type="task_submission",
        entity_id=submission.id,
        new_value={"task_id": task.id, "user_id": participant.id, "points": task.points},
    )
    await safe_send(
        bot,
        participant.telegram_id,
        f"Ваш результат по заданию одобрен.\n\n{task.title}\n\nНачислено: {task.points} баллов",
    )
    await call.message.answer("Результат одобрен. Баллы начислены.")


@router.callback_query(F.data.startswith("admin:tasksub:reject:"))
async def task_submission_reject(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    submission, task, participant = await _submission_context(
        session, int(call.data.rsplit(":", 1)[-1])
    )
    if not submission or not task or not participant:
        await call.message.answer("Результат не найден")
        return
    submission.status = "rejected"
    submission.reviewed_by = user.id if user else None
    await safe_send(
        bot,
        participant.telegram_id,
        f"Результат по заданию не принят.\n\n{task.title}\n\nБаллы не начислены.",
    )
    await audit(
        session,
        actor_id=user.id if user else None,
        action="task_submission.rejected",
        entity_type="task_submission",
        entity_id=submission.id,
    )
    await call.message.answer("Результат отклонён. Баллы не начислены.")


@router.callback_query(F.data.startswith("admin:tasksub:comment:"))
async def task_submission_comment_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    submission_id = int(call.data.rsplit(":", 1)[-1])
    submission = await session.get(TaskSubmission, submission_id)
    if not submission:
        await call.message.answer("Результат не найден")
        return
    await state.set_state(AdminTaskReviewStates.comment)
    await state.update_data(task_submission_id=submission_id)
    await call.message.answer(
        "Напишите комментарий участнику.\n\n"
        "Например: что исправить, что добавить или какой материал прислать повторно."
    )


@router.message(AdminTaskReviewStates.comment)
async def task_submission_comment_send(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    submission, task, participant = await _submission_context(
        session, int(data["task_submission_id"])
    )
    if not submission or not task or not participant:
        await state.clear()
        await message.answer("Результат не найден")
        return
    comment = (message.text or "").strip()
    if not comment:
        await message.answer("Комментарий не может быть пустым")
        return
    submission.status = "needs_revision"
    submission.reviewed_by = user.id if user else None
    submission.admin_comment = comment
    task.status = "review"
    await safe_send(
        bot,
        participant.telegram_id,
        f"Комментарий по заданию:\n\n{task.title}\n\n{comment}\n\n"
        "Доработайте результат и отправьте его повторно через Личный кабинет → Мои задачи.",
    )
    await audit(
        session,
        actor_id=user.id if user else None,
        action="task_submission.needs_revision",
        entity_type="task_submission",
        entity_id=submission.id,
        new_value={"comment": comment},
    )
    await state.clear()
    await message.answer("Комментарий отправлен участнику. Результат переведён на доработку.")
