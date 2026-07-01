from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import Settings
from app.database.models import User
from app.states.task import TaskStates
from app.utils import texts
from app.utils.constants import PRIVILEGED_ROLES
from app.utils.validators import clean_text, parse_deadline, parse_time

router = Router(name="leader_task_deadline_buttons")

DEADLINE_PARSE_ERROR = """Не получилось распознать дедлайн.

Можно написать так:
15.07.2026 18:30
15.07 18:30
завтра 18:00
сегодня 20:00
18:00"""


def _deadline_day_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ Сегодня", callback_data="task:deadline:day:0"),
                InlineKeyboardButton(text="🌅 Завтра", callback_data="task:deadline:day:1"),
            ],
            [
                InlineKeyboardButton(text="🗓 Через 3 дня", callback_data="task:deadline:day:3"),
                InlineKeyboardButton(text="📆 Через неделю", callback_data="task:deadline:day:7"),
            ],
            [InlineKeyboardButton(text="✍️ Ввести вручную", callback_data="task:deadline:manual")],
        ]
    )


def _deadline_time_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10:00", callback_data="task:deadline:time:10:00"),
                InlineKeyboardButton(text="12:00", callback_data="task:deadline:time:12:00"),
            ],
            [
                InlineKeyboardButton(text="15:00", callback_data="task:deadline:time:15:00"),
                InlineKeyboardButton(text="18:00", callback_data="task:deadline:time:18:00"),
            ],
            [InlineKeyboardButton(text="20:00", callback_data="task:deadline:time:20:00")],
            [InlineKeyboardButton(text="✍️ Ввести время вручную", callback_data="task:deadline:manual_time")],
            [InlineKeyboardButton(text="🔁 Изменить дату", callback_data="task:deadline:restart")],
        ]
    )


def _deadline_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="task:deadline:confirm")],
            [InlineKeyboardButton(text="🔁 Изменить", callback_data="task:deadline:restart")],
        ]
    )


async def _guard(message: Message | CallbackQuery, user: User | None) -> bool:
    target = message.message if isinstance(message, CallbackQuery) else message
    if not user or user.is_blocked or user.role not in PRIVILEGED_ROLES:
        if isinstance(message, CallbackQuery):
            await message.answer()
        await target.answer(texts.NO_ACCESS)
        return False
    return True


@router.message(TaskStates.description)
async def task_description_with_deadline_buttons(
    message: Message, state: FSMContext, user: User | None
) -> None:
    if not await _guard(message, user):
        return
    value = clean_text(message.text or "", 2000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(task_description=value)
    await state.set_state(TaskStates.deadline)
    await message.answer("Выберите дедлайн задачи:", reply_markup=_deadline_day_keyboard())


@router.callback_query(TaskStates.deadline, F.data.startswith("task:deadline:day:"))
async def task_deadline_day(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await call.answer()
    try:
        offset_days = int(call.data.rsplit(":", 1)[-1])
    except ValueError:
        return
    tz = ZoneInfo(settings.timezone)
    target_date = datetime.now(tz).date() + timedelta(days=offset_days)
    await state.update_data(task_deadline_date=target_date.isoformat())
    await call.message.answer("Выберите время дедлайна:", reply_markup=_deadline_time_keyboard())


@router.callback_query(TaskStates.deadline, F.data.startswith("task:deadline:time:"))
async def task_deadline_time(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await call.answer()
    raw_time = call.data.split("task:deadline:time:", 1)[-1]
    parsed_time = parse_time(raw_time)
    if parsed_time is None:
        return
    data = await state.get_data()
    raw_date = data.get("task_deadline_date")
    if not raw_date:
        await call.message.answer("Сначала выберите дату дедлайна.", reply_markup=_deadline_day_keyboard())
        return
    tz = ZoneInfo(settings.timezone)
    selected_date = datetime.fromisoformat(raw_date).date()
    deadline = datetime.combine(selected_date, parsed_time, tzinfo=tz)
    if deadline <= datetime.now(tz):
        await call.message.answer(
            "Это время уже прошло. Выберите другое время или поставьте дедлайн на завтра.",
            reply_markup=_deadline_time_keyboard(),
        )
        return
    await state.update_data(task_deadline_candidate=deadline.isoformat())
    await call.message.answer(
        f"Дедлайн задачи:\n\n{deadline:%d.%m.%Y, %H:%M}\n\nПодтвердить?",
        reply_markup=_deadline_confirm_keyboard(),
    )


@router.callback_query(TaskStates.deadline, F.data == "task:deadline:manual_time")
async def task_deadline_manual_time(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(task_deadline_manual_mode="time")
    await call.message.answer("Напишите время дедлайна в формате ЧЧ:ММ")


@router.callback_query(TaskStates.deadline, F.data == "task:deadline:manual")
async def task_deadline_manual(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(task_deadline_manual_mode="full")
    await call.message.answer(DEADLINE_PARSE_ERROR)


@router.callback_query(TaskStates.deadline, F.data == "task:deadline:restart")
async def task_deadline_restart(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(
        task_deadline_date=None,
        task_deadline_candidate=None,
        task_deadline_manual_mode=None,
    )
    await call.message.answer("Выберите дедлайн задачи:", reply_markup=_deadline_day_keyboard())


@router.callback_query(TaskStates.deadline, F.data == "task:deadline:confirm")
async def task_deadline_confirm(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    data = await state.get_data()
    raw_deadline = data.get("task_deadline_candidate")
    if not raw_deadline:
        await call.message.answer("Сначала выберите дату и время дедлайна.", reply_markup=_deadline_day_keyboard())
        return
    await state.update_data(task_deadline=datetime.fromisoformat(raw_deadline))
    await state.set_state(TaskStates.points)
    await call.message.answer("Укажите количество баллов после подтверждения задачи.")


@router.message(TaskStates.deadline)
async def task_deadline_manual_input(message: Message, state: FSMContext, settings: Settings) -> None:
    data = await state.get_data()
    mode = data.get("task_deadline_manual_mode")
    tz = ZoneInfo(settings.timezone)
    if mode == "time":
        raw_date = data.get("task_deadline_date")
        parsed_time = parse_time(message.text or "")
        if not raw_date or parsed_time is None:
            await message.answer("Проверьте время. Формат: ЧЧ:ММ")
            return
        selected_date = datetime.fromisoformat(raw_date).date()
        deadline = datetime.combine(selected_date, parsed_time, tzinfo=tz)
        if deadline <= datetime.now(tz):
            await message.answer(
                "Это время уже прошло. Выберите другое время или поставьте дедлайн на завтра.",
                reply_markup=_deadline_time_keyboard(),
            )
            return
    else:
        deadline = parse_deadline(message.text or "", settings.timezone)
        if deadline is None:
            await message.answer(DEADLINE_PARSE_ERROR)
            return
    await state.update_data(task_deadline_candidate=deadline.isoformat())
    await message.answer(
        f"Дедлайн задачи:\n\n{deadline:%d.%m.%Y, %H:%M}\n\nПодтвердить?",
        reply_markup=_deadline_confirm_keyboard(),
    )
