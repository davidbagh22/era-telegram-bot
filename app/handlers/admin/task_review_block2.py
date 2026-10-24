from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Task, TaskSubmission, User
from app.services import task_review_service
from app.services.authorization_service import can_manage_tasks
from app.services.notification_service import safe_answer_media, safe_send
from app.utils import texts

router = Router(name="admin_task_review_block2")


class TaskReviewStates(StatesGroup):
    revision_comment = State()
    reject_comment = State()


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return can_manage_tasks(user, settings, telegram_id)


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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить и начислить баллы", callback_data=f"admin:tasksub:approve:{submission_id}")],
        [InlineKeyboardButton(text="💬 Вернуть на доработку", callback_data=f"admin:tasksub:revision:{submission_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:tasksub:reject:{submission_id}")],
    ])


def _task_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать задание или конкурс", callback_data="admin:task:new")],
        [InlineKeyboardButton(text="📥 Результаты на проверке", callback_data="admin:task_submissions")],
        [InlineKeyboardButton(text="← События", callback_data="admin:menu:activity")],
    ])


async def _context(session: AsyncSession, submission_id: int) -> tuple[TaskSubmission | None, Task | None, User | None]:
    submission = await session.get(TaskSubmission, submission_id)
    if not submission:
        return None, None, None
    task = await session.get(Task, submission.task_id)
    participant = await session.get(User, submission.user_id)
    return submission, task, participant


async def _send_file(message: Message, file_id: str) -> None:
    if not await safe_answer_media(message, file_id, caption="Файл результата"):
        await message.answer("Файл прикреплён, но Telegram не дал открыть его повторно.")


async def _send_submission_card(message: Message, session: AsyncSession, submission_id: int, user=None, settings=None) -> None:
    submission, task, participant = await _context(session, submission_id)
    if not submission or not task or not participant:
        await message.answer("Результат не найден")
        return
    if not await task_review_service.can_review_task(session, user, settings, task):
        await message.answer(texts.NO_ACCESS)
        return
    telegram = f"@{participant.username}" if participant.username else str(participant.telegram_id)
    status = {"pending": "на проверке", "approved": "одобрено", "rejected": "отклонено", "needs_revision": "на доработке"}.get(submission.status, submission.status)
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
        reply_markup=_review_keyboard(submission.id) if submission.status == 'pending' else None,
    )
    if submission.file_id:
        await _send_file(message, submission.file_id)


@router.callback_query(F.data == "admin:tasks")
async def tasks_menu(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer("✅ Задания\n\nПроверка результатов, доработки и начисление баллов.", reply_markup=_task_menu())


@router.callback_query(F.data == "admin:task_submissions")
async def task_submissions(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    submissions = await task_review_service.list_pending_submissions(session, reviewer=user, settings=settings)
    if not submissions:
        await call.message.answer("Результатов заданий на проверке пока нет.", reply_markup=_task_menu())
        return
    await call.message.answer(f"Результаты на проверке: {len(submissions)}")
    for submission in submissions:
        await _send_submission_card(call.message, session, submission.id, user, settings)


@router.callback_query(F.data.startswith("admin:tasksub:approve:"))
async def approve_submission(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(call, user, settings):
        return
    submission, task, participant = await _context(session, int(call.data.rsplit(":", 1)[-1]))
    if not submission or not task or not participant:
        await call.message.answer("Результат не найден")
        return
    if not await task_review_service.can_review_task(session, user, settings, task):
        await call.message.answer(texts.NO_ACCESS)
        return
    result = await task_review_service.decide_submission(
        session, submission, task, participant, action="approve", comment="", actor=user, settings=settings
    )
    await session.commit()
    if result.participant_notice:
        await safe_send(bot, participant.telegram_id, result.participant_notice)
    await call.message.answer(result.admin_notice)


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
    if not await task_review_service.can_review_task(session, user, settings, task):
        await message.answer(texts.NO_ACCESS)
        return
    comment = (message.text or "").strip()[:2000]
    if not comment:
        await message.answer("Комментарий обязателен")
        return
    result = await task_review_service.decide_submission(
        session, submission, task, participant, action="revision", comment=comment, actor=user, settings=settings
    )
    await session.commit()
    if result.participant_notice:
        await safe_send(bot, participant.telegram_id, result.participant_notice)
    await state.clear()
    await message.answer(result.admin_notice)


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
    if not await task_review_service.can_review_task(session, user, settings, task):
        await message.answer(texts.NO_ACCESS)
        return
    comment = (message.text or "").strip()[:2000]
    if not comment:
        await message.answer("Причина обязательна")
        return
    result = await task_review_service.decide_submission(
        session, submission, task, participant, action="reject", comment=comment, actor=user, settings=settings
    )
    await session.commit()
    if result.participant_notice:
        await safe_send(bot, participant.telegram_id, result.participant_notice)
    await state.clear()
    await message.answer(result.admin_notice)


def _attention_version(task: Task) -> str:
    import hashlib
    from datetime import timezone
    def stamp(value):
        if value is None:
            return ''
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()
    return hashlib.sha256(f'{task.status}|{stamp(task.deadline)}|{stamp(task.updated_at)}'.encode()).hexdigest()[:10]


async def _attention_guard(call, user, settings, session):
    from app.services.staff_access_service import can_operate_queue
    allowed = await can_operate_queue(session, user, settings, 'tasks.manage', telegram_id=call.from_user.id)
    if not allowed or user is None or user.telegram_id != call.from_user.id:
        await call.answer('Доступ отсутствует.', show_alert=True)
        return False
    return True


@router.callback_query(F.data.regexp(r'^admin:taskattention:page:\d+$'), F.message.chat.type == 'private')
async def task_attention_queue(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession):
    from datetime import datetime, timezone
    from html import escape
    from sqlalchemy import func, select
    from app.services.analytics_snapshot_service import task_attention_condition
    from app.utils.telegram import edit_text_or_answer
    if not await _attention_guard(call, user, settings, session):
        return
    await call.answer()
    condition = task_attention_condition(datetime.now(timezone.utc))
    total = int(await session.scalar(select(func.count()).select_from(Task).where(condition)) or 0)
    page = min(int(call.data.rsplit(':', 1)[-1]), max(0, (total-1)//8))
    tasks = (await session.scalars(select(Task).where(condition).order_by(Task.deadline.asc().nullslast(), Task.id).offset(page*8).limit(8))).all()
    rows = [[InlineKeyboardButton(text=f'#{task.id} {task.title[:45]}', callback_data=f'admin:taskattention:item:{task.id}')] for task in tasks]
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(text='←', callback_data=f'admin:taskattention:page:{page-1}'))
    if (page+1)*8 < total:
        navigation.append(InlineKeyboardButton(text='→', callback_data=f'admin:taskattention:page:{page+1}'))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text='← Сводка', callback_data='admin:management:open')])
    text = f'<b>Задачи требуют внимания: {total}</b>\n\n' + ('\n'.join(f'#{task.id} {escape(task.title[:100])}' for task in tasks) or 'Открытых проблем нет.')
    await edit_text_or_answer(call.message, text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.regexp(r'^admin:taskattention:(item:\d+|(cancel|confirm|extend):\d+:[a-f0-9]{10})$'), F.message.chat.type == 'private')
async def task_attention_action(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from app.services.leaders_workspace import change_task, TERMINAL
    from app.services.leaders_workcenter_service import render_task_card
    from app.utils.telegram import edit_text_or_answer
    if not await _attention_guard(call, user, settings, session):
        return
    parts = call.data.split(':')
    action, task_id = parts[2], int(parts[3])
    task = await session.scalar(select(Task).where(Task.id == task_id).with_for_update().execution_options(populate_existing=True))
    if task is None or task.status in TERMINAL:
        await call.answer('Задача уже закрыта или удалена. Обновите список.', show_alert=True)
        return
    version = _attention_version(task)
    if action != 'item' and parts[4] != version:
        await call.answer('Задача изменилась. Откройте её заново.', show_alert=True)
        return
    if action == 'confirm':
        pending_result = await session.scalar(
            select(TaskSubmission.id).where(
                TaskSubmission.task_id == task.id,
                TaskSubmission.status == 'pending',
            ).limit(1)
        )
        if pending_result is not None:
            await call.answer(
                'Нельзя отменить задачу: сначала проверьте отправленный результат.',
                show_alert=True,
            )
            return
    if action in {'confirm', 'extend'}:
        try:
            await change_task(session, settings, task, user, 'cancel' if action == 'confirm' else 'deadline',
                              value=datetime.now(timezone.utc)+timedelta(days=7) if action == 'extend' else None)
            await session.commit()
            await session.refresh(task)
        except ValueError as exc:
            await session.rollback()
            await call.answer(str(exc), show_alert=True)
            return
        version = _attention_version(task)
    await call.answer()
    rows = []
    if task.status not in TERMINAL:
        if action == 'cancel':
            rows.append([InlineKeyboardButton(text='Подтвердить отмену задачи', callback_data=f'admin:taskattention:confirm:{task.id}:{version}')])
            rows.append([InlineKeyboardButton(text='Оставить задачу', callback_data=f'admin:taskattention:item:{task.id}')])
        else:
            rows.append([InlineKeyboardButton(text='Результаты на проверке', callback_data='admin:task_submissions')])
            rows.append([InlineKeyboardButton(text='Срок: 7 дней с сегодняшнего дня', callback_data=f'admin:taskattention:extend:{task.id}:{version}')])
            rows.append([InlineKeyboardButton(text='Отменить задачу', callback_data=f'admin:taskattention:cancel:{task.id}:{version}')])
    rows.append([InlineKeyboardButton(text='← Требуют внимания', callback_data='admin:taskattention:page:0')])
    assignee = await session.get(User, task.assignee_id) if task.assignee_id else None
    await edit_text_or_answer(call.message, render_task_card(task, assignee), parse_mode='HTML', reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
