from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Task, User
from app.services import leader_service
from app.services.notification_service import notify_admins
from app.states.open_task import OpenTaskStates
from app.utils import texts
from app.utils.constants import PRIVILEGED_ROLES
from app.utils.validators import clean_text, parse_deadline, parse_time

router = Router(name="leader_open_tasks")

DEADLINE_PARSE_ERROR = """Не получилось распознать дедлайн.

Можно написать так:
15.07.2026 18:30
15.07 18:30
завтра 18:00
сегодня 20:00
18:00"""

TASK_POINT_PRESETS = {40, 80, 150, 200}
TASK_POINT_PROMPT = (
    "Выберите баллы по сложности:\n\n"
    "40 — лёгкая\n"
    "80 — стандартная\n"
    "150 — сложная\n"
    "200 — высокая ответственность"
)


def _day_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ Сегодня", callback_data="opentask:deadline:day:0"),
                InlineKeyboardButton(text="🌅 Завтра", callback_data="opentask:deadline:day:1"),
            ],
            [
                InlineKeyboardButton(text="🗓 Через 3 дня", callback_data="opentask:deadline:day:3"),
                InlineKeyboardButton(text="📆 Через неделю", callback_data="opentask:deadline:day:7"),
            ],
            [InlineKeyboardButton(text="✍️ Ввести вручную", callback_data="opentask:deadline:manual")],
        ]
    )


def _time_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10:00", callback_data="opentask:deadline:time:10:00"),
                InlineKeyboardButton(text="12:00", callback_data="opentask:deadline:time:12:00"),
            ],
            [
                InlineKeyboardButton(text="15:00", callback_data="opentask:deadline:time:15:00"),
                InlineKeyboardButton(text="18:00", callback_data="opentask:deadline:time:18:00"),
            ],
            [InlineKeyboardButton(text="20:00", callback_data="opentask:deadline:time:20:00")],
            [InlineKeyboardButton(text="✍️ Ввести время вручную", callback_data="opentask:deadline:manual_time")],
            [InlineKeyboardButton(text="🔁 Изменить дату", callback_data="opentask:deadline:restart")],
        ]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="opentask:deadline:confirm")],
            [InlineKeyboardButton(text="🔁 Изменить", callback_data="opentask:deadline:restart")],
        ]
    )


def _application_keyboard(task_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"leader:taskapp:accept:{task_id}:{user_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"leader:taskapp:reject:{task_id}:{user_id}"),
            ]
        ]
    )


async def _guard(event: Message | CallbackQuery, user: User | None) -> bool:
    message = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await event.answer()
    if not user or user.is_blocked or user.role not in PRIVILEGED_ROLES:
        await message.answer(texts.NO_ACCESS)
        return False
    return True


@router.callback_query(F.data == "leader:task:open")
async def open_task_start(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    if not await _guard(call, user):
        return
    await state.clear()
    await state.set_state(OpenTaskStates.title)
    await call.message.answer(
        "Как называется открытая задача?\n\nНапример: Нужны помощники для съёмки мероприятия"
    )


@router.message(OpenTaskStates.title)
async def open_task_title(message: Message, state: FSMContext) -> None:
    title = clean_text(message.text or "", 255)
    if not title:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(open_task_title=title)
    await state.set_state(OpenTaskStates.description)
    await message.answer(
        "Опишите задачу и что должен сделать помощник.\n\n"
        "Например: прийти на мероприятие, снять 10–15 кадров и передать материалы медиа-команде."
    )


@router.message(OpenTaskStates.description)
async def open_task_description(message: Message, state: FSMContext) -> None:
    description = clean_text(message.text or "", 2000)
    if not description:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(open_task_description=description)
    await state.set_state(OpenTaskStates.deadline)
    await message.answer("Выберите дедлайн открытой задачи:", reply_markup=_day_keyboard())


@router.callback_query(OpenTaskStates.deadline, F.data.startswith("opentask:deadline:day:"))
async def open_task_deadline_day(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await call.answer()
    offset_days = int(call.data.rsplit(":", 1)[-1])
    tz = ZoneInfo(settings.timezone)
    selected_date = datetime.now(tz).date() + timedelta(days=offset_days)
    await state.update_data(open_task_deadline_date=selected_date.isoformat())
    await call.message.answer("Выберите время дедлайна:", reply_markup=_time_keyboard())


@router.callback_query(OpenTaskStates.deadline, F.data.startswith("opentask:deadline:time:"))
async def open_task_deadline_time(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await call.answer()
    raw_time = call.data.split("opentask:deadline:time:", 1)[-1]
    selected_time = parse_time(raw_time)
    if selected_time is None:
        return
    data = await state.get_data()
    raw_date = data.get("open_task_deadline_date")
    if not raw_date:
        await call.message.answer("Сначала выберите дату дедлайна.", reply_markup=_day_keyboard())
        return
    tz = ZoneInfo(settings.timezone)
    selected_date = datetime.fromisoformat(raw_date).date()
    deadline = datetime.combine(selected_date, selected_time, tzinfo=tz)
    if deadline <= datetime.now(tz):
        await call.message.answer(
            "Это время уже прошло. Выберите другое время или поставьте дедлайн на завтра.",
            reply_markup=_time_keyboard(),
        )
        return
    await state.update_data(open_task_deadline_candidate=deadline.isoformat())
    await call.message.answer(
        f"Дедлайн задачи:\n\n{deadline:%d.%m.%Y, %H:%M}\n\nПодтвердить?",
        reply_markup=_confirm_keyboard(),
    )


@router.callback_query(OpenTaskStates.deadline, F.data == "opentask:deadline:manual_time")
async def open_task_manual_time(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(open_task_deadline_manual_mode="time")
    await call.message.answer("Напишите время дедлайна в формате ЧЧ:ММ")


@router.callback_query(OpenTaskStates.deadline, F.data == "opentask:deadline:manual")
async def open_task_manual(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(open_task_deadline_manual_mode="full")
    await call.message.answer(DEADLINE_PARSE_ERROR)


@router.callback_query(OpenTaskStates.deadline, F.data == "opentask:deadline:restart")
async def open_task_deadline_restart(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(
        open_task_deadline_date=None,
        open_task_deadline_candidate=None,
        open_task_deadline_manual_mode=None,
    )
    await call.message.answer("Выберите дедлайн открытой задачи:", reply_markup=_day_keyboard())


@router.callback_query(OpenTaskStates.deadline, F.data == "opentask:deadline:confirm")
async def open_task_deadline_confirm(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    data = await state.get_data()
    raw_deadline = data.get("open_task_deadline_candidate")
    if not raw_deadline:
        await call.message.answer("Сначала выберите дату и время дедлайна.", reply_markup=_day_keyboard())
        return
    await state.update_data(open_task_deadline=datetime.fromisoformat(raw_deadline))
    await state.set_state(OpenTaskStates.points)
    await call.message.answer(TASK_POINT_PROMPT)


@router.message(OpenTaskStates.deadline)
async def open_task_deadline_manual_input(message: Message, state: FSMContext, settings: Settings) -> None:
    data = await state.get_data()
    mode = data.get("open_task_deadline_manual_mode")
    tz = ZoneInfo(settings.timezone)
    if mode == "time":
        raw_date = data.get("open_task_deadline_date")
        selected_time = parse_time(message.text or "")
        if not raw_date or selected_time is None:
            await message.answer("Проверьте время. Формат: ЧЧ:ММ")
            return
        selected_date = datetime.fromisoformat(raw_date).date()
        deadline = datetime.combine(selected_date, selected_time, tzinfo=tz)
        if deadline <= datetime.now(tz):
            await message.answer(
                "Это время уже прошло. Выберите другое время или поставьте дедлайн на завтра.",
                reply_markup=_time_keyboard(),
            )
            return
    else:
        deadline = parse_deadline(message.text or "", settings.timezone)
        if deadline is None:
            await message.answer(DEADLINE_PARSE_ERROR)
            return
    await state.update_data(open_task_deadline_candidate=deadline.isoformat())
    await message.answer(
        f"Дедлайн задачи:\n\n{deadline:%d.%m.%Y, %H:%M}\n\nПодтвердить?",
        reply_markup=_confirm_keyboard(),
    )


@router.message(OpenTaskStates.points)
async def open_task_points(message: Message, state: FSMContext) -> None:
    try:
        points = int(message.text or "")
    except ValueError:
        await message.answer(TASK_POINT_PROMPT)
        return
    if points not in TASK_POINT_PRESETS:
        await message.answer("Можно выбрать только 40, 80, 150 или 200 баллов.\n\n" + TASK_POINT_PROMPT)
        return
    await state.update_data(open_task_points=points)
    await state.set_state(OpenTaskStates.max_participants)
    await message.answer("Сколько помощников нужно? Укажите число от 1 до 50.")


@router.message(OpenTaskStates.max_participants)
async def open_task_finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    try:
        max_participants = int(message.text or "")
        if not 1 <= max_participants <= 50:
            raise ValueError
    except ValueError:
        await message.answer("Укажите число от 1 до 50.")
        return
    data = await state.get_data()
    task = await leader_service.create_open_task(
        session,
        creator=user,
        title=data["open_task_title"],
        description=data["open_task_description"],
        deadline=data["open_task_deadline"],
        points=data["open_task_points"],
        max_participants=max_participants,
    )
    await state.clear()
    await message.answer(
        "Открытая задача опубликована. Участники смогут откликнуться в личном кабинете → мои задачи."
    )
    await notify_admins(
        bot,
        settings,
        f"📢 Открытая задача опубликована\n\n{task.title}\nЛидер: {user.first_name} {user.last_name or ''}\nНужно помощников: {max_participants}",
    )


@router.callback_query(F.data == "leader:task:applications")
async def open_task_applications(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if not await _guard(call, user):
        return
    results = await leader_service.list_open_tasks_with_applications(session, user)
    if not results:
        await call.message.answer("Открытых задач с заявками пока нет.")
        return
    found = False
    for result in results:
        task = result.task
        if not result.applications:
            continue
        found = True
        lines = [
            f"📢 #{task.id} {task.title}",
            f"Дедлайн: {task.deadline:%d.%m.%Y %H:%M}",
            f"Нужно помощников: {task.max_participants or 'без ограничения'}",
            "",
            "Отклики:",
        ]
        for application in result.applications:
            person = application.applicant
            participant = application.participant
            username = f"@{person.username}" if person.username else "без username"
            status = {
                "pending": "на рассмотрении",
                "accepted": "принят",
                "joined": "в команде",
                "rejected": "отклонён",
            }.get(participant.status, participant.status)
            lines.append(f"• {person.first_name} {person.last_name or ''} — {username} — {status}")
            if participant.status == "pending":
                await call.message.answer(
                    "\n".join(lines),
                    reply_markup=_application_keyboard(task.id, person.id),
                )
                lines = []
        if lines:
            await call.message.answer("\n".join(lines))
    if not found:
        await call.message.answer("Заявок на открытые задачи пока нет.")


@router.callback_query(F.data.regexp(r"^leader:taskapp:(accept|reject):\d+:\d+$"))
async def open_task_application_action(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user):
        return
    _, _, action, raw_task_id, raw_user_id = call.data.split(":")
    task = await session.get(Task, int(raw_task_id))
    target = await session.get(User, int(raw_user_id))
    if task is None or target is None or task.creator_id != user.id:
        await call.message.answer(texts.NO_ACCESS)
        return
    try:
        await leader_service.decide_task_application(
            session, task=task, target=target, action=action, actor=user, bot=bot
        )
    except ValueError as exc:
        if str(exc) == "capacity_reached":
            await call.message.answer("Команда уже набрана. Увеличьте лимит или отклоните лишние заявки.")
        else:
            await call.message.answer("Заявка уже не найдена.")
        return
    if action == "accept":
        await call.message.answer(f"Заявка принята: {target.first_name} {target.last_name or ''}")
    else:
        await call.message.answer(f"Заявка отклонена: {target.first_name} {target.last_name or ''}")
