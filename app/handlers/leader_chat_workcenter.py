from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.fsm.context import FSMContext
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Task, TaskDelivery, TaskSubmission, User
from app.services.audit_service import audit
from app.services import task_review_service
from app.services.leaders_workcenter_service import (
    card_snapshot,
    render_task_card,
    task_card_keyboard,
)
from app.services.weekly_pulse_cycle_service import upsert_leader_membership
from app.states.task import LeadersChatTaskStates
from app.keyboards.participant import open_app_button
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, TaskStatus

router = Router(name="leaders_chat_workcenter")


def _is_active_member(status: str, is_member: bool | None = None) -> bool:
    return status in {"creator", "administrator", "member"} or (
        status == "restricted" and is_member is True
    )


def _mention(user: User) -> str:
    label = escape(f"{user.first_name} {user.last_name or ''}".strip())
    if user.username:
        return f"@{escape(user.username)}"
    return f'<a href="tg://user?id={user.telegram_id}">{label}</a>'


def _can_create(user: User | None, settings: Settings, telegram_id: int | None) -> bool:
    if telegram_id and telegram_id in settings.admin_ids:
        return True
    return bool(user and user.role in PRIVILEGED_ROLES)


@router.chat_member()
async def track_leaders_membership(
    event: ChatMemberUpdated,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not settings.leaders_chat_id or event.chat.id != settings.leaders_chat_id:
        return
    member = event.new_chat_member
    user = member.user
    status = member.status
    is_member = getattr(member, "is_member", None)
    await upsert_leader_membership(
        session,
        leader_chat_id=event.chat.id,
        telegram_user_id=user.id,
        membership_status=status,
        username=user.username,
        display_name=user.full_name,
        is_member=is_member,
    )


@router.message(CommandStart(deep_link=True), F.chat.type == "private")
async def connect_pulse_from_deep_link(
    message: Message,
    command: CommandStart,
    bot,
    settings: Settings,
    session: AsyncSession,
) -> None:
    """One-time self-sync for members already in Leaders when the feature launches."""
    payload = command.args or ""
    if not payload.startswith("pulse_connect") or not settings.leaders_chat_id or not message.from_user:
        return
    member = await bot.get_chat_member(settings.leaders_chat_id, message.from_user.id)
    if not _is_active_member(member.status, getattr(member, "is_member", None)):
        await message.answer("Подключить Пульс могут только участники чата «ЛИДЕРЫ».")
        return
    await upsert_leader_membership(
        session,
        leader_chat_id=settings.leaders_chat_id,
        telegram_user_id=message.from_user.id,
        membership_status=member.status,
        username=message.from_user.username,
        display_name=message.from_user.full_name,
        is_member=getattr(member, "is_member", None),
    )
    await message.answer(
        "Готово. Аккаунт связан с чатом «ЛИДЕРЫ». Откройте Weekly Pulse в приложении ЭРА.",
        reply_markup=open_app_button(
            settings.effective_miniapp_url, "Открыть Weekly Pulse"
        ),
    )


@router.message(Command("task"), F.chat.type.in_({"group", "supergroup"}))
async def begin_group_task(
    message: Message,
    state: FSMContext,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not settings.leaders_chat_id or message.chat.id != settings.leaders_chat_id:
        return
    if not _can_create(user, settings, message.from_user.id if message.from_user else None):
        await message.reply("Создавать задачи в рабочем чате могут только руководители.")
        return
    if user is None and message.from_user:
        user = await session.scalar(select(User).where(User.telegram_id == message.from_user.id))
    if user is None:
        await message.reply("Сначала войдите в ERA-бот и завершите регистрацию, затем повторите команду.")
        return
    source = message.reply_to_message
    title = (source.text or source.caption or "").strip() if source else ""
    if not title:
        await message.reply("Ответьте командой /task на сообщение с поручением.")
        return
    await state.clear()
    await state.update_data(
        task_title=title[:255],
        task_description=title[:2000],
        task_chat_id=message.chat.id,
        task_thread_id=message.message_thread_id,
        task_reply_message_id=source.message_id,
        task_creator_id=user.id,
    )
    await state.set_state(LeadersChatTaskStates.assignee)
    await message.reply("Кому поручить? Отправьте @username или имя участника.")


async def _card_task(
    call: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> Task | None:
    message = call.message
    if (
        not settings.leaders_chat_id
        or message is None
        or message.chat.id != settings.leaders_chat_id
    ):
        return None
    task_id = None
    try:
        task_id = int((call.data or "").rsplit(":", 1)[-1])
    except (TypeError, ValueError):
        return None
    delivery = await session.scalar(
        select(TaskDelivery).where(
            TaskDelivery.task_id == task_id,
            TaskDelivery.chat_key == "leaders",
            TaskDelivery.chat_id == message.chat.id,
            TaskDelivery.telegram_message_id == message.message_id,
            TaskDelivery.status == "sent",
        )
    )
    return await session.get(Task, task_id) if delivery else None


@router.callback_query(F.data.startswith("leaders_task:"))
async def handle_leaders_task_card_action(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    user: User | None,
    event_from_user,
    bot,
) -> None:
    parts = (call.data or "").split(":")
    action = parts[1] if len(parts) >= 3 else ""
    task = await _card_task(call, session, settings)
    if task is None:
        await call.answer("Карточка задачи больше недоступна.", show_alert=True)
        return
    if action in {"start", "submit", "block"}:
        if user is None or task.assignee_id != user.id:
            await call.answer("Это действие доступно исполнителю задачи.", show_alert=True)
            return
        if action == "start":
            if task.status not in {TaskStatus.NEW, TaskStatus.PUBLISHED}:
                await call.answer("Задача уже изменила статус.", show_alert=True)
                return
            task.status = TaskStatus.IN_PROGRESS
            await audit(
                session,
                actor_id=user.id,
                action="task.started_from_leaders_chat",
                entity_type="task",
                entity_id=task.id,
            )
            await call.answer("Задача отмечена как начатая.")
            if call.message:
                await call.message.reply("🟡 Принято. Статус карточки обновится автоматически.")
            return
        if action == "submit":
            if task.status not in {TaskStatus.NEW, TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS}:
                await call.answer("Сейчас результат отправить нельзя.", show_alert=True)
                return
            await state.clear()
            await state.update_data(leaders_task_id=task.id, leaders_task_chat_id=call.message.chat.id)
            await state.set_state(LeadersChatTaskStates.result)
            await call.answer()
            await call.message.reply("Напишите результат выполнения одним сообщением.")
            return
        await state.clear()
        await state.update_data(leaders_task_id=task.id, leaders_task_chat_id=call.message.chat.id)
        await state.set_state(LeadersChatTaskStates.blocker)
        await call.answer()
        await call.message.reply("Кратко опишите, что мешает и какая помощь нужна.")
        return

    if action in {"accept", "return"}:
        if not _can_create(user, settings, event_from_user.id if event_from_user else None):
            await call.answer("Проверять результаты могут только руководители.", show_alert=True)
            return
        if action == "return":
            await state.clear()
            await state.update_data(leaders_task_id=task.id, leaders_task_chat_id=call.message.chat.id)
            await state.set_state(LeadersChatTaskStates.review_comment)
            await call.answer()
            await call.message.reply("Напишите комментарий, что нужно доработать.")
            return
        submission = await session.scalar(
            select(TaskSubmission)
            .where(TaskSubmission.task_id == task.id, TaskSubmission.status == "pending")
            .order_by(TaskSubmission.id.desc())
        )
        assignee = await session.get(User, task.assignee_id) if task.assignee_id else None
        if submission is None or assignee is None:
            await call.answer("На проверке нет актуального результата.", show_alert=True)
            return
        result = await task_review_service.decide_submission(
            session,
            submission,
            task,
            assignee,
            action="approve",
            comment="",
            actor=user,
        )
        await call.answer("Результат принят. Баллы начислены по правилам ЭРА.")
        if result.participant_notice:
            try:
                await bot.send_message(assignee.telegram_id, result.participant_notice)
            except TelegramAPIError:
                pass
        return
    await call.answer()


@router.message(LeadersChatTaskStates.result, F.chat.type.in_({"group", "supergroup"}))
async def save_leaders_task_result(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    user: User | None,
) -> None:
    data = await state.get_data()
    if (
        not settings.leaders_chat_id
        or message.chat.id != settings.leaders_chat_id
        or data.get("leaders_task_chat_id") != message.chat.id
        or not user
    ):
        await state.clear()
        return
    task = await session.get(Task, data.get("leaders_task_id"))
    text = (message.text or message.caption or "").strip()
    if task is None or task.assignee_id != user.id or not text:
        await message.reply("Не удалось сохранить результат. Начните сдачу из карточки задачи.")
        await state.clear()
        return
    previous = await session.scalar(
        select(TaskSubmission).where(
            TaskSubmission.task_id == task.id,
            TaskSubmission.user_id == user.id,
            TaskSubmission.status == "pending",
        )
    )
    if previous is None:
        session.add(TaskSubmission(task_id=task.id, user_id=user.id, text=text[:5000], status="pending"))
    else:
        previous.text = text[:5000]
    task.status = TaskStatus.REVIEW
    await audit(
        session,
        actor_id=user.id,
        action="task.submitted_from_leaders_chat",
        entity_type="task",
        entity_id=task.id,
    )
    await state.clear()
    await message.reply(f"Результат задачи #{task.id} отправлен на проверку.")


@router.message(LeadersChatTaskStates.blocker, F.chat.type.in_({"group", "supergroup"}))
async def save_leaders_task_blocker(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    user: User | None,
) -> None:
    data = await state.get_data()
    task = await session.get(Task, data.get("leaders_task_id"))
    blocker = (message.text or "").strip()
    if (
        not settings.leaders_chat_id
        or message.chat.id != settings.leaders_chat_id
        or data.get("leaders_task_chat_id") != message.chat.id
        or not user
        or task is None
        or task.assignee_id != user.id
        or not blocker
    ):
        await state.clear()
        await message.reply("Не удалось сохранить блокер. Начните действие из карточки задачи.")
        return
    task.comment = blocker[:1000]
    if task.status in {TaskStatus.NEW, TaskStatus.PUBLISHED}:
        task.status = TaskStatus.IN_PROGRESS
    await audit(
        session,
        actor_id=user.id,
        action="task.blocker_reported_from_leaders_chat",
        entity_type="task",
        entity_id=task.id,
        new_value={"comment": task.comment},
    )
    await state.clear()
    await message.reply(f"Блокер по задаче #{task.id} сохранён и будет виден в админке.")


@router.message(LeadersChatTaskStates.review_comment, F.chat.type.in_({"group", "supergroup"}))
async def return_leaders_task_result(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    user: User | None,
    event_from_user,
    bot,
) -> None:
    data = await state.get_data()
    if not _can_create(user, settings, event_from_user.id if event_from_user else None):
        await state.clear()
        return
    if (
        not settings.leaders_chat_id
        or message.chat.id != settings.leaders_chat_id
        or data.get("leaders_task_chat_id") != message.chat.id
    ):
        await state.clear()
        return
    task = await session.get(Task, data.get("leaders_task_id"))
    submission = await session.scalar(
        select(TaskSubmission)
        .where(
            TaskSubmission.task_id == data.get("leaders_task_id"),
            TaskSubmission.status == "pending",
        )
        .order_by(TaskSubmission.id.desc())
    )
    assignee = await session.get(User, task.assignee_id) if task and task.assignee_id else None
    comment = (message.text or "").strip()
    if task is None or submission is None or assignee is None or not comment:
        await state.clear()
        await message.reply("Не удалось вернуть результат. Проверьте задачу и отправьте комментарий снова.")
        return
    result = await task_review_service.decide_submission(
        session,
        submission,
        task,
        assignee,
        action="revision",
        comment=comment[:2000],
        actor=user,
    )
    await audit(
        session,
        actor_id=user.id,
        action="task.result_returned_from_leaders_chat",
        entity_type="task",
        entity_id=task.id,
    )
    if result.participant_notice:
        try:
            await bot.send_message(assignee.telegram_id, result.participant_notice)
        except TelegramAPIError:
            pass
    await state.clear()
    await message.reply(f"Задача #{task.id} возвращена исполнителю на доработку.")


@router.message(LeadersChatTaskStates.assignee, F.chat.type.in_({"group", "supergroup"}))
async def find_group_task_assignee(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    user: User | None,
    event_from_user,
) -> None:
    if not settings.leaders_chat_id or message.chat.id != settings.leaders_chat_id:
        return
    if not _can_create(user, settings, event_from_user.id if event_from_user else None):
        await state.clear()
        return
    query = (message.text or "").strip().lstrip("@").lower()
    if not query:
        await message.reply("Укажите @username или имя участника.")
        return
    filters = [User.first_name.ilike(f"%{query}%"), User.last_name.ilike(f"%{query}%")]
    if query.isdigit():
        filters.append(User.telegram_id == int(query))
    if "@" in (message.text or "") or " " not in query:
        filters.append(User.username.ilike(query))
    users = list(
        (
            await session.scalars(
                select(User)
                .where(
                    User.application_status == ApplicationStatus.APPROVED,
                    User.is_blocked.is_(False),
                    User.is_archived.is_(False),
                    or_(*filters),
                )
                .order_by(User.first_name)
                .limit(8)
            )
        ).all()
    )
    if not users:
        await message.reply("Не нашёл участника. Проверьте username или имя.")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{item.first_name} {item.last_name or ''}".strip(),
                    callback_data=f"leaders_task:assign:{item.id}",
                )
            ]
            for item in users
        ]
    )
    await message.reply("Выберите исполнителя:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("leaders_task:assign:"))
async def choose_group_task_assignee(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    user: User | None,
    event_from_user,
) -> None:
    await call.answer()
    if not settings.leaders_chat_id or not call.message or call.message.chat.id != settings.leaders_chat_id:
        return
    if await state.get_state() != LeadersChatTaskStates.assignee.state:
        return
    if not _can_create(user, settings, event_from_user.id if event_from_user else None):
        await state.clear()
        return
    data = await state.get_data()
    if data.get("task_creator_id") != getattr(user, "id", None):
        await state.clear()
        return
    try:
        assignee_id = int(call.data.rsplit(":", 1)[-1])
    except (TypeError, ValueError):
        return
    assignee = await session.get(User, assignee_id)
    if assignee is None:
        await call.message.answer("Участник больше недоступен. Начните создание задачи заново.")
        await state.clear()
        return
    await state.update_data(task_assignee_id=assignee.id)
    await state.set_state(LeadersChatTaskStates.deadline)
    await call.message.answer("Укажите срок в формате ДД.ММ.ГГГГ ЧЧ:ММ.")


@router.message(LeadersChatTaskStates.deadline, F.chat.type.in_({"group", "supergroup"}))
async def finish_group_task(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    user: User | None,
    bot,
) -> None:
    if not settings.leaders_chat_id or message.chat.id != settings.leaders_chat_id:
        return
    if not _can_create(user, settings, message.from_user.id if message.from_user else None):
        await state.clear()
        return
    data = await state.get_data()
    if data.get("task_creator_id") != getattr(user, "id", None):
        await state.clear()
        return
    try:
        deadline = datetime.strptime(message.text or "", "%d.%m.%Y %H:%M").replace(
            tzinfo=ZoneInfo(settings.timezone)
        )
    except ValueError:
        await message.reply("Проверьте формат: ДД.ММ.ГГГГ ЧЧ:ММ.")
        return
    if deadline <= datetime.now(ZoneInfo(settings.timezone)):
        await message.reply("Срок уже прошёл. Укажите будущую дату и время.")
        return
    creator = await session.get(User, data.get("task_creator_id"))
    assignee = await session.get(User, data.get("task_assignee_id"))
    if creator is None or assignee is None:
        await state.clear()
        await message.reply("Не удалось подтвердить автора или исполнителя. Создайте задачу заново.")
        return
    task = Task(
        title=data["task_title"],
        description=data["task_description"],
        assignee_id=assignee.id,
        creator_id=creator.id,
        deadline=deadline,
        remind_at=deadline - timedelta(hours=24),
        points=80,
        task_type="private",
    )
    session.add(task)
    await session.flush()
    mention = _mention(assignee)
    card = None
    delivery_error = None
    try:
        card = await bot.send_message(
            chat_id=data["task_chat_id"],
            message_thread_id=data.get("task_thread_id"),
            text=render_task_card(task, assignee),
            parse_mode=ParseMode.HTML,
            reply_markup=task_card_keyboard(task, settings),
        )
    except TelegramAPIError as exc:
        delivery_error = str(exc)[:2000]
    session.add(
        TaskDelivery(
            task_id=task.id,
            chat_key="leaders",
            chat_id=data["task_chat_id"],
            telegram_message_id=card.message_id if card else None,
            message_thread_id=data.get("task_thread_id"),
            status="sent" if card else "failed",
            error=delivery_error,
            sent_at=datetime.now().astimezone() if card else None,
            reminder_count=0,
            remind_at=(deadline - timedelta(hours=24)) if card else None,
            last_card_snapshot=card_snapshot(task, assignee) if card else {},
        )
    )
    await audit(
        session,
        actor_id=creator.id,
        action="task.created_from_leaders_chat",
        entity_type="task",
        entity_id=task.id,
        new_value={
            "chat_id": data["task_chat_id"],
            "message_id": card.message_id if card else None,
            "delivery_error": delivery_error,
        },
    )
    suffix = "Карточка опубликована в рабочем чате." if card else "Задача сохранена, но карточку не удалось отправить."
    await message.reply(f"Задача #{task.id} создана. Исполнитель: {mention}. {suffix}")
    await state.clear()
