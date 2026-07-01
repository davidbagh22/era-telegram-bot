from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Badge, Task, User, UserBadge
from app.keyboards.admin import application_actions
from app.keyboards.participant import main_menu
from app.services.audit_service import audit
from app.services.notification_service import safe_send
from app.states.admin import AdminGrowthStates
from app.utils import texts
from app.utils.constants import ApplicationStatus, ParticipationStatus, PERMISSIONS, Role
from app.utils.validators import clean_text, parse_deadline, parse_time

router = Router(name="admin_addons")


class AdminBadgeStates(StatesGroup):
    name = State()
    description = State()


class AdminTaskFixStates(StatesGroup):
    person = State()
    title = State()
    description = State()
    photo = State()
    deadline = State()
    points = State()


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


def _tg(user: User) -> str:
    return f"@{user.username}" if user.username else str(user.telegram_id)


def _application_text(target: User) -> str:
    departments = ", ".join(x.department.name for x in target.departments) or "не выбраны"
    directions = ", ".join(x.direction.name for x in target.directions) or "не выбраны"
    return (
        f"📝 Заявка #{target.id}\n\n"
        f"👤 {target.first_name} {target.last_name or ''}\n"
        f"Возраст: {target.age or 'не указан'}\n"
        f"Город: {target.city or 'не указан'}\n"
        f"Телефон: {target.phone or 'не указан'}\n"
        f"Telegram: {_tg(target)}\n"
        f"Email: {target.email or 'не указан'}\n\n"
        f"Департаменты: {departments}\n"
        f"Направления: {directions}\n"
        f"Время: {target.available_time or 'не указано'}\n"
        f"Путь: {target.desired_path or 'не указан'}\n\n"
        f"Учёба / работа: {target.education_work or 'не указано'}\n"
        f"Занятие: {target.occupation or 'не указано'}\n\n"
        f"Мотивация:\n{target.motivation or 'не указана'}"
    )


@router.callback_query(F.data == "admin:applications")
async def applications_full(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    pending = (
        await session.scalars(
            select(User)
            .where(
                User.application_status.in_(
                    [ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]
                )
            )
            .order_by(User.created_at)
        )
    ).all()
    if not pending:
        await call.message.answer("Новых заявок участников нет.")
        return
    await call.message.answer(f"Новые заявки: {len(pending)}")
    for target in pending:
        await call.message.answer(
            _application_text(target),
            reply_markup=application_actions(target.id),
        )


@router.callback_query(F.data == "admin:points")
async def points_menu(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Начислить или списать баллы", callback_data="admin:growth:start:points")],
            [InlineKeyboardButton(text="Вручить знак", callback_data="admin:growth:start:badge")],
            [InlineKeyboardButton(text="🏅 Список знаков", callback_data="admin:badges")],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:menu:growth")],
        ]
    )
    await call.message.answer("⭐ Баллы и знаки", reply_markup=keyboard)


@router.callback_query(F.data == "admin:badges")
async def badges_menu(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    badges = (await session.scalars(select(Badge).order_by(Badge.id))).all()
    rows = [[InlineKeyboardButton(text="➕ Добавить знак", callback_data="admin:badge:new")]]
    for badge in badges:
        rows.append(
            [InlineKeyboardButton(text=f"#{badge.id} · {badge.name}", callback_data=f"admin:badge:edit:{badge.id}")]
        )
    rows.append([InlineKeyboardButton(text="← Баллы и знаки", callback_data="admin:points")])
    await call.message.answer(
        "🏅 Знаки\n\nСписок идёт по возрастанию: от первого/младшего к более высоким.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "admin:badge:new")
async def badge_new_start(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminBadgeStates.name)
    await state.update_data(badge_mode="new")
    await call.message.answer("Название нового знака")


@router.callback_query(F.data.startswith("admin:badge:edit:"))
async def badge_edit_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    badge = await session.get(Badge, int(call.data.rsplit(":", 1)[-1]))
    if not badge:
        await call.message.answer("Знак не найден")
        return
    await state.set_state(AdminBadgeStates.name)
    await state.update_data(badge_mode="edit", badge_id=badge.id)
    await call.message.answer(f"Текущее название: {badge.name}\n\nНапишите новое название")


@router.message(AdminBadgeStates.name)
async def badge_name(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 100)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(badge_name=value)
    await state.set_state(AdminBadgeStates.description)
    await message.answer("Описание знака. Можно написать '-' если описание не нужно")


@router.message(AdminBadgeStates.description)
async def badge_save(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(message, user, settings):
        return
    value = clean_text(message.text or "", 1000)
    description = None if value == "-" else value
    data = await state.get_data()
    if data.get("badge_mode") == "edit":
        badge = await session.get(Badge, int(data["badge_id"]))
        if badge:
            badge.name = data["badge_name"]
            badge.description = description
            await message.answer("Знак обновлён")
    else:
        session.add(Badge(name=data["badge_name"], description=description))
        await message.answer("Знак добавлен")
    await state.clear()


@router.callback_query(AdminGrowthStates.person, F.data.startswith("admin:growth:person:"))
async def growth_select_person_filtered(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    target_id = int(call.data.rsplit(":", 1)[-1])
    data = await state.get_data()
    await state.update_data(growth_target_id=target_id)
    if data.get("growth_action") == "points":
        await state.set_state(AdminGrowthStates.points)
        await call.message.answer(
            "Сколько баллов изменить?\n\nПоложительное число начислит баллы, отрицательное — спишет"
        )
        return
    owned_ids = set(
        (
            await session.scalars(
                select(UserBadge.badge_id).where(UserBadge.user_id == target_id)
            )
        ).all()
    )
    badges = (
        await session.scalars(
            select(Badge).where(~Badge.id.in_(owned_ids or {-1})).order_by(Badge.id)
        )
    ).all()
    if not badges:
        await state.clear()
        await call.message.answer("У пользователя уже есть все доступные знаки")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"#{badge.id} · {badge.name}", callback_data=f"admin:growth:badge:{badge.id}")]
            for badge in badges
        ]
    )
    await call.message.answer("Какой знак вручить? Уже выданные знаки не показываются.", reply_markup=keyboard)


# ---------- Новое создание админского задания ----------


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отменить", callback_data="admin:task:cancel")]]
    )


def _photo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить фото", callback_data="admin:task:photo:skip")],
            [InlineKeyboardButton(text="Отменить", callback_data="admin:task:cancel")],
        ]
    )


def _deadline_day_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сегодня", callback_data="admin:task:deadline:day:0"),
                InlineKeyboardButton(text="Завтра", callback_data="admin:task:deadline:day:1"),
            ],
            [
                InlineKeyboardButton(text="Через 3 дня", callback_data="admin:task:deadline:day:3"),
                InlineKeyboardButton(text="Через неделю", callback_data="admin:task:deadline:day:7"),
            ],
            [InlineKeyboardButton(text="Ввести вручную", callback_data="admin:task:deadline:manual")],
            [InlineKeyboardButton(text="Отменить", callback_data="admin:task:cancel")],
        ]
    )


def _deadline_time_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10:00", callback_data="admin:task:deadline:time:10:00"),
                InlineKeyboardButton(text="12:00", callback_data="admin:task:deadline:time:12:00"),
            ],
            [
                InlineKeyboardButton(text="15:00", callback_data="admin:task:deadline:time:15:00"),
                InlineKeyboardButton(text="18:00", callback_data="admin:task:deadline:time:18:00"),
            ],
            [InlineKeyboardButton(text="20:00", callback_data="admin:task:deadline:time:20:00")],
            [InlineKeyboardButton(text="Ввести время вручную", callback_data="admin:task:deadline:manual_time")],
            [InlineKeyboardButton(text="Изменить дату", callback_data="admin:task:deadline:restart")],
        ]
    )


@router.callback_query(F.data == "admin:tasks")
async def admin_tasks_menu(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    await call.message.answer(
        "✅ Задания\n\nСоздайте задание участнику. Можно прикрепить фото и выбрать дедлайн кнопками.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Дать задание участнику", callback_data="admin:task:new")],
                [InlineKeyboardButton(text="← Назад", callback_data="admin:menu:activity")],
            ]
        ),
    )


@router.callback_query(F.data == "admin:task:new")
async def admin_task_new(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminTaskFixStates.person)
    await call.message.answer("Кому дать задание? Напишите имя, фамилию, @username или Telegram ID", reply_markup=_cancel_keyboard())


@router.callback_query(F.data == "admin:task:cancel")
async def admin_task_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await call.message.answer("Создание задания отменено")


@router.message(AdminTaskFixStates.person)
async def admin_task_person(
    message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession
) -> None:
    if not await _guard(message, user, settings):
        return
    query = clean_text(message.text or "", 150).lstrip("@").lower()
    conditions = [
        User.first_name.ilike(f"%{query}%"),
        User.last_name.ilike(f"%{query}%"),
        User.username.ilike(f"%{query}%"),
    ]
    if query.isdigit():
        conditions.append(User.telegram_id == int(query))
    targets = (await session.scalars(select(User).where(or_(*conditions), User.is_archived.is_(False)).limit(8))).all()
    if not targets:
        await message.answer("Участник не найден. Попробуйте ещё раз", reply_markup=_cancel_keyboard())
        return
    await message.answer(
        "Выберите участника",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"{target.first_name} {target.last_name or ''}".strip(), callback_data=f"admin:task:person:{target.id}")]
                for target in targets
            ]
            + [[InlineKeyboardButton(text="Отменить", callback_data="admin:task:cancel")]]
        ),
    )


@router.callback_query(AdminTaskFixStates.person, F.data.startswith("admin:task:person:"))
async def admin_task_person_select(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(task_target_id=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(AdminTaskFixStates.title)
    await call.message.answer("Название задания", reply_markup=_cancel_keyboard())


@router.message(AdminTaskFixStates.title)
async def admin_task_title(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(task_title=value)
    await state.set_state(AdminTaskFixStates.description)
    await message.answer("Описание задания", reply_markup=_cancel_keyboard())


@router.message(AdminTaskFixStates.description)
async def admin_task_description(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 2000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(task_description=value)
    await state.set_state(AdminTaskFixStates.photo)
    await message.answer("Прикрепите фото к заданию или пропустите этот шаг", reply_markup=_photo_keyboard())


@router.callback_query(AdminTaskFixStates.photo, F.data == "admin:task:photo:skip")
async def admin_task_photo_skip(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(task_file_id=None)
    await state.set_state(AdminTaskFixStates.deadline)
    await call.message.answer("Выберите дедлайн", reply_markup=_deadline_day_keyboard())


@router.message(AdminTaskFixStates.photo, F.photo | F.document)
async def admin_task_photo(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    await state.update_data(task_file_id=file_id)
    await state.set_state(AdminTaskFixStates.deadline)
    await message.answer("Фото прикреплено. Теперь выберите дедлайн", reply_markup=_deadline_day_keyboard())


@router.callback_query(AdminTaskFixStates.deadline, F.data.startswith("admin:task:deadline:day:"))
async def admin_task_deadline_day(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await call.answer()
    days = int(call.data.rsplit(":", 1)[-1])
    selected = datetime.now(ZoneInfo(settings.timezone)).date() + timedelta(days=days)
    await state.update_data(task_deadline_date=selected.isoformat(), task_deadline_manual_mode=None)
    await call.message.answer("Выберите время", reply_markup=_deadline_time_keyboard())


@router.callback_query(AdminTaskFixStates.deadline, F.data.startswith("admin:task:deadline:time:"))
async def admin_task_deadline_time(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await call.answer()
    raw_time = call.data.split("admin:task:deadline:time:", 1)[-1]
    selected_time = parse_time(raw_time)
    data = await state.get_data()
    selected_date = datetime.fromisoformat(data["task_deadline_date"]).date()
    deadline = datetime.combine(selected_date, selected_time, tzinfo=ZoneInfo(settings.timezone))
    if deadline <= datetime.now(ZoneInfo(settings.timezone)):
        await call.message.answer("Это время уже прошло. Выберите другое.", reply_markup=_deadline_time_keyboard())
        return
    await state.update_data(task_deadline=deadline)
    await state.set_state(AdminTaskFixStates.points)
    await call.message.answer(f"Дедлайн: {deadline:%d.%m.%Y %H:%M}\n\nСколько баллов начислить за выполнение?")


@router.callback_query(AdminTaskFixStates.deadline, F.data == "admin:task:deadline:manual")
async def admin_task_deadline_manual(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(task_deadline_manual_mode="full")
    await call.message.answer("Напишите дедлайн: 15.07 18:30, завтра 18:00 или 18:00", reply_markup=_cancel_keyboard())


@router.callback_query(AdminTaskFixStates.deadline, F.data == "admin:task:deadline:manual_time")
async def admin_task_deadline_manual_time(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(task_deadline_manual_mode="time")
    await call.message.answer("Напишите время в формате ЧЧ:ММ", reply_markup=_cancel_keyboard())


@router.callback_query(AdminTaskFixStates.deadline, F.data == "admin:task:deadline:restart")
async def admin_task_deadline_restart(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(task_deadline_date=None, task_deadline_manual_mode=None)
    await call.message.answer("Выберите дедлайн", reply_markup=_deadline_day_keyboard())


@router.message(AdminTaskFixStates.deadline)
async def admin_task_deadline_text(message: Message, state: FSMContext, settings: Settings) -> None:
    data = await state.get_data()
    tz = ZoneInfo(settings.timezone)
    if data.get("task_deadline_manual_mode") == "time":
        selected_time = parse_time(message.text or "")
        raw_date = data.get("task_deadline_date")
        if not selected_time or not raw_date:
            await message.answer("Проверьте время. Формат: ЧЧ:ММ", reply_markup=_cancel_keyboard())
            return
        deadline = datetime.combine(datetime.fromisoformat(raw_date).date(), selected_time, tzinfo=tz)
        if deadline <= datetime.now(tz):
            await message.answer("Это время уже прошло. Выберите другое.", reply_markup=_deadline_time_keyboard())
            return
    else:
        deadline = parse_deadline(message.text or "", settings.timezone)
        if deadline is None:
            await message.answer("Не понял дедлайн. Пример: завтра 18:00 или 15.07 18:30", reply_markup=_cancel_keyboard())
            return
    await state.update_data(task_deadline=deadline)
    await state.set_state(AdminTaskFixStates.points)
    await message.answer(f"Дедлайн: {deadline:%d.%m.%Y %H:%M}\n\nСколько баллов начислить за выполнение?")


@router.message(AdminTaskFixStates.points)
async def admin_task_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    try:
        points = int((message.text or "").strip())
        if not 0 <= points <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 0 до 1000")
        return
    data = await state.get_data()
    target = await session.get(User, int(data["task_target_id"]))
    if target is None:
        await state.clear()
        await message.answer("Участник не найден")
        return
    task = Task(
        title=data["task_title"],
        description=data["task_description"],
        assignee_id=target.id,
        creator_id=user.id if user else target.id,
        deadline=data["task_deadline"],
        points=points,
        status="published",
        file_id=data.get("task_file_id"),
        task_type="private",
    )
    session.add(task)
    await session.flush()
    await audit(session, actor_id=user.id if user else None, action="task.admin_created", entity_type="task", entity_id=task.id)
    await state.clear()
    await message.answer("Задание создано и отправлено участнику")
    notice = (
        f"✅ Новое задание ЭРА\n\n{task.title}\n\n{task.description}\n\n"
        f"Дедлайн: {task.deadline:%d.%m.%Y %H:%M}\nБаллы: {task.points}\n\n"
        "Откройте Личный кабинет → Мои задачи"
    )
    if task.file_id:
        try:
            await bot.send_photo(target.telegram_id, task.file_id, caption=notice)
        except Exception:
            await bot.send_document(target.telegram_id, task.file_id, caption=notice)
    else:
        await safe_send(bot, target.telegram_id, notice)
