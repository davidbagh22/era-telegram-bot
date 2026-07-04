from __future__ import annotations

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    Department,
    Direction,
    Event,
    MonthlyGoal,
    Office,
    OrganizationContact,
    PointTransaction,
    Project,
    Task,
    User,
    UserDepartment,
    UserDirection,
)
from app.services.excel_service import build_analytics_workbook
from app.utils.constants import ApplicationStatus, Role
from app.utils.validators import clean_text

router = Router(name="admin_management_v3")


class GoalStates(StatesGroup):
    period = State()
    title = State()
    metric = State()
    target = State()
    edit_value = State()


class ContactStates(StatesGroup):
    organization = State()
    contact_name = State()
    position_primary = State()
    position_secondary = State()
    email = State()
    phone = State()
    notes = State()


class ContentEditStates(StatesGroup):
    description = State()


class OfficeEditStates(StatesGroup):
    value = State()


class ChatBroadcastStates(StatesGroup):
    text = State()
    confirm = State()


def _keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _back(callback: str) -> InlineKeyboardMarkup:
    return _keyboard([[InlineKeyboardButton(text="← Назад", callback_data=callback)]])


async def _guard(event: CallbackQuery | Message, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
    else:
        message = event
    allowed = bool(user and user.role == Role.ADMIN) or (
        getattr(event, "from_user", None)
        and event.from_user.id in settings.admin_ids
    )
    if not allowed:
        await message.answer("Этот раздел доступен администратору")
        return False
    return True


def _raw(value) -> str:
    return str(value.value if hasattr(value, "value") else value)


async def _analytics_data(session: AsyncSession) -> dict:
    users = (
        await session.scalars(
            select(User)
            .where(User.is_archived.is_(False))
            .order_by(User.first_name, User.last_name)
        )
    ).all()
    events = (await session.scalars(select(Event).order_by(Event.event_date.desc()))).all()
    projects = (await session.scalars(select(Project).order_by(Project.created_at.desc()))).all()
    tasks = (await session.scalars(select(Task))).all()
    departments = (await session.scalars(select(Department).order_by(Department.name))).all()
    directions = (await session.scalars(select(Direction).order_by(Direction.name))).all()
    user_departments = (await session.scalars(select(UserDepartment))).all()
    user_directions = (await session.scalars(select(UserDirection))).all()
    goals = (await session.scalars(select(MonthlyGoal).order_by(MonthlyGoal.period.desc()))).all()
    contacts = (
        await session.scalars(
            select(OrganizationContact)
            .where(OrganizationContact.is_active.is_(True))
            .order_by(OrganizationContact.organization, OrganizationContact.contact_name)
        )
    ).all()
    point_rows = (
        await session.execute(
            select(PointTransaction.user_id, PointTransaction.points)
        )
    ).all()
    point_totals: dict[int, int] = {}
    for user_id, points in point_rows:
        point_totals[user_id] = point_totals.get(user_id, 0) + int(points)

    department_names = {item.id: item.name for item in departments}
    direction_names = {item.id: item.name for item in directions}
    direction_department = {item.id: item.department_id for item in directions}

    department_stats = []
    for department in departments:
        department_goals = [g for g in goals if g.department_id == department.id and g.scope_type == "department"]
        department_stats.append(
            {
                "id": department.id,
                "name": department.name,
                "members": sum(x.department_id == department.id for x in user_departments),
                "directions": sum(x.department_id == department.id for x in directions),
                "projects": sum(x.department_id == department.id for x in projects),
                "events": sum(x.department_id == department.id for x in events),
                "tasks_completed": sum(
                    x.department_id == department.id and _raw(x.status) == "completed"
                    for x in tasks
                ),
                "goals_active": sum(x.status == "active" for x in department_goals),
                "goals_completed": sum(x.status == "completed" for x in department_goals),
            }
        )

    direction_stats = []
    for direction in directions:
        direction_goals = [g for g in goals if g.direction_id == direction.id and g.scope_type == "direction"]
        direction_stats.append(
            {
                "id": direction.id,
                "department": department_names.get(direction.department_id, "—"),
                "name": direction.name,
                "members": sum(x.direction_id == direction.id for x in user_directions),
                "projects": sum(x.direction_id == direction.id for x in projects),
                "events": sum(x.direction_id == direction.id for x in events),
                "tasks_completed": sum(
                    x.direction_id == direction.id and _raw(x.status) == "completed"
                    for x in tasks
                ),
                "goals_active": sum(x.status == "active" for x in direction_goals),
                "goals_completed": sum(x.status == "completed" for x in direction_goals),
            }
        )

    for goal in goals:
        if goal.scope_type == "department":
            goal.scope_name = department_names.get(goal.department_id, "—")
        else:
            goal.scope_name = direction_names.get(goal.direction_id, "—")

    return {
        "users": users,
        "events": events,
        "projects": projects,
        "tasks": tasks,
        "departments": departments,
        "directions": directions,
        "goals": goals,
        "contacts": contacts,
        "point_totals": point_totals,
        "department_stats": department_stats,
        "direction_stats": direction_stats,
        "direction_department": direction_department,
    }


def _analytics_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [
                InlineKeyboardButton(text="👥 Участники", callback_data="admin:analytics:view:users"),
                InlineKeyboardButton(text="🏛 Департаменты", callback_data="admin:analytics:view:departments"),
            ],
            [
                InlineKeyboardButton(text="🧭 Направления", callback_data="admin:analytics:view:directions"),
                InlineKeyboardButton(text="📅 Проекты и события", callback_data="admin:analytics:view:activity"),
            ],
            [InlineKeyboardButton(text="🎯 Ежемесячные цели", callback_data="admin:goals")],
            [InlineKeyboardButton(text="📥 Скачать полный Excel", callback_data="admin:analytics:download:all")],
            [
                InlineKeyboardButton(text="Excel: участники", callback_data="admin:analytics:download:users"),
                InlineKeyboardButton(text="Excel: подразделения", callback_data="admin:analytics:download:departments"),
            ],
            [InlineKeyboardButton(text="← Управление", callback_data="admin:menu:system")],
        ]
    )


@router.callback_query(F.data == "admin:analytics")
async def analytics_home(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    data = await _analytics_data(session)
    approved = sum(x.application_status == ApplicationStatus.APPROVED for x in data["users"])
    completed_projects = sum(_raw(x.status) == "completed" for x in data["projects"])
    completed_events = sum(_raw(x.status) == "completed" for x in data["events"])
    await call.message.answer(
        "📊 Аналитика ЭРА\n\n"
        f"Участники: {len(data['users'])} · одобрены: {approved}\n"
        f"Департаменты: {len(data['departments'])}\n"
        f"Направления: {len(data['directions'])}\n"
        f"Проекты: {len(data['projects'])} · завершены: {completed_projects}\n"
        f"Мероприятия: {len(data['events'])} · завершены: {completed_events}\n"
        f"Активные цели: {sum(x.status == 'active' for x in data['goals'])}\n\n"
        "Выберите срез или скачайте оформленный Excel",
        reply_markup=_analytics_keyboard(),
    )


@router.callback_query(F.data.startswith("admin:analytics:view:"))
async def analytics_view(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    kind = call.data.rsplit(":", 1)[-1]
    data = await _analytics_data(session)
    if kind == "users":
        roles: dict[str, int] = {}
        cities: dict[str, int] = {}
        for item in data["users"]:
            roles[_raw(item.role)] = roles.get(_raw(item.role), 0) + 1
            city = item.city or "Не указан"
            cities[city] = cities.get(city, 0) + 1
        role_labels = {"participant": "Участники", "activist": "Активисты", "leader": "Лидеры", "head": "Руководители", "council": "Совет", "admin": "Администраторы"}
        lines = ["👥 Участники", ""] + [
            f"{role_labels.get(key, key)}: {value}" for key, value in sorted(roles.items())
        ]
        lines += ["", "Города:"] + [
            f"• {name}: {count}" for name, count in sorted(cities.items(), key=lambda x: x[1], reverse=True)[:10]
        ]
    elif kind == "departments":
        lines = ["🏛 Работа департаментов", ""]
        for item in data["department_stats"]:
            lines += [
                f"{item['name']}",
                f"Участники: {item['members']} · направления: {item['directions']}",
                f"Проекты: {item['projects']} · мероприятия: {item['events']}",
                f"Выполненные задачи: {item['tasks_completed']} · цели: {item['goals_completed']}/{item['goals_active'] + item['goals_completed']}",
                "",
            ]
    elif kind == "directions":
        lines = ["🧭 Активность направлений", ""]
        for item in data["direction_stats"]:
            lines += [
                f"{item['name']} · {item['department']}",
                f"Участники: {item['members']} · проекты: {item['projects']} · события: {item['events']}",
                f"Выполненные задачи: {item['tasks_completed']} · целей завершено: {item['goals_completed']}",
                "",
            ]
    else:
        project_statuses: dict[str, int] = {}
        event_statuses: dict[str, int] = {}
        for item in data["projects"]:
            project_statuses[_raw(item.status)] = project_statuses.get(_raw(item.status), 0) + 1
        for item in data["events"]:
            event_statuses[_raw(item.status)] = event_statuses.get(_raw(item.status), 0) + 1
        lines = ["📅 Проекты и мероприятия", "", "Проекты по статусам:"]
        lines += [f"• {key}: {value}" for key, value in sorted(project_statuses.items())]
        lines += ["", "Мероприятия по статусам:"]
        lines += [f"• {key}: {value}" for key, value in sorted(event_statuses.items())]
    await call.message.answer("\n".join(lines), reply_markup=_back("admin:analytics"))


@router.callback_query(F.data.startswith("admin:analytics:download:"))
async def analytics_download(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    kind = call.data.rsplit(":", 1)[-1]
    data = await _analytics_data(session)
    sections = None
    if kind == "users":
        sections = {"summary", "users"}
    elif kind == "departments":
        sections = {"summary", "departments", "directions", "goals"}
    content = build_analytics_workbook(
        data["users"],
        data["events"],
        data["projects"],
        data["point_totals"],
        department_stats=data["department_stats"],
        direction_stats=data["direction_stats"],
        goals=data["goals"],
        contacts=data["contacts"],
        sections=sections,
    )
    suffix = {"users": "uchastniki", "departments": "podrazdeleniya"}.get(kind, "polnaya")
    await call.message.answer_document(
        BufferedInputFile(content, filename=f"ERA_analitika_{suffix}.xlsx"),
        caption="Готово. Таблица оформлена на русском, с фильтрами, сводкой и отдельными листами",
        reply_markup=_back("admin:analytics"),
    )


def _goals_keyboard(goals: list[MonthlyGoal]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="➕ Новая цель", callback_data="admin:goals:new")]]
    for goal in goals[:20]:
        icon = "✅" if goal.status == "completed" else "🎯"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {goal.period} · {goal.title[:35]}",
                callback_data=f"admin:goal:view:{goal.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="← Аналитика", callback_data="admin:analytics")])
    return _keyboard(rows)


@router.callback_query(F.data == "admin:goals")
async def goals_menu(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    goals = (
        await session.scalars(
            select(MonthlyGoal)
            .where(MonthlyGoal.status.in_(["active", "completed"]))
            .order_by(MonthlyGoal.period.desc(), MonthlyGoal.id.desc())
        )
    ).all()
    await call.message.answer(
        "🎯 Ежемесячные цели\n\n"
        "Цели можно назначать департаменту или направлению, менять план и факт, завершать и редактировать",
        reply_markup=_goals_keyboard(list(goals)),
    )


@router.callback_query(F.data == "admin:goals:new")
async def goal_new(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    await call.message.answer(
        "Для кого создаём цель?",
        reply_markup=_keyboard([
            [InlineKeyboardButton(text="Департамент", callback_data="admin:goal:scope:department")],
            [InlineKeyboardButton(text="Направление", callback_data="admin:goal:scope:direction")],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:goals")],
        ]),
    )


@router.callback_query(F.data.startswith("admin:goal:scope:"))
async def goal_scope(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    scope = call.data.rsplit(":", 1)[-1]
    if scope == "department":
        items = (await session.scalars(select(Department).order_by(Department.name))).all()
    else:
        items = (await session.scalars(select(Direction).order_by(Direction.name))).all()
    await state.update_data(goal_scope=scope)
    rows = [[InlineKeyboardButton(text=item.name, callback_data=f"admin:goal:target:{scope}:{item.id}")] for item in items]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="admin:goals")])
    await call.message.answer("Выберите подразделение", reply_markup=_keyboard(rows))


@router.callback_query(F.data.startswith("admin:goal:target:"))
async def goal_target(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, scope, target_id = call.data.split(":")
    current = datetime.now().astimezone().strftime("%Y-%m")
    await state.update_data(goal_scope=scope, goal_target_id=int(target_id))
    await state.set_state(GoalStates.period)
    await call.message.answer(
        "Укажите месяц в формате ГГГГ-ММ",
        reply_markup=_keyboard([
            [InlineKeyboardButton(text=f"Текущий месяц · {current}", callback_data=f"admin:goal:period:{current}")],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:goals")],
        ]),
    )


async def _goal_period_saved(message: Message, value: str, state: FSMContext) -> None:
    try:
        datetime.strptime(value, "%Y-%m")
    except ValueError:
        await message.answer("Проверьте формат. Пример: 2026-07")
        return
    await state.update_data(goal_period=value)
    await state.set_state(GoalStates.title)
    await message.answer("Коротко сформулируйте цель")


@router.callback_query(GoalStates.period, F.data.startswith("admin:goal:period:"))
async def goal_period_button(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await _goal_period_saved(call.message, call.data.rsplit(":", 1)[-1], state)


@router.message(GoalStates.period)
async def goal_period_message(message: Message, state: FSMContext) -> None:
    await _goal_period_saved(message, (message.text or "").strip(), state)


@router.message(GoalStates.title)
async def goal_title(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 255)
    if not value:
        await message.answer("Напишите название цели")
        return
    await state.update_data(goal_title=value)
    await state.set_state(GoalStates.metric)
    await message.answer("Что измеряем? Например: проведённые мероприятия, участники, публикации")


@router.message(GoalStates.metric)
async def goal_metric(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 100)
    if not value:
        await message.answer("Напишите название показателя")
        return
    await state.update_data(goal_metric=value)
    await state.set_state(GoalStates.target)
    await message.answer("Укажите план целым числом")


@router.message(GoalStates.target)
async def goal_target_value(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    try:
        target = int((message.text or "").strip())
        if target < 1:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число больше нуля")
        return
    data = await state.get_data()
    scope = data["goal_scope"]
    goal = MonthlyGoal(
        period=data["goal_period"],
        scope_type=scope,
        department_id=data["goal_target_id"] if scope == "department" else None,
        direction_id=data["goal_target_id"] if scope == "direction" else None,
        title=data["goal_title"],
        metric=data["goal_metric"],
        target_value=target,
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(goal)
    await session.flush()
    await state.clear()
    await message.answer(
        "Цель создана и сразу появится в аналитике",
        reply_markup=_keyboard([[InlineKeyboardButton(text="Открыть цель", callback_data=f"admin:goal:view:{goal.id}")]]),
    )


@router.callback_query(F.data.startswith("admin:goal:view:"))
async def goal_view(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    goal = await session.get(MonthlyGoal, int(call.data.rsplit(":", 1)[-1]))
    if goal is None:
        await call.message.answer("Цель не найдена")
        return
    if goal.scope_type == "department":
        target = await session.get(Department, goal.department_id)
    else:
        target = await session.get(Direction, goal.direction_id)
    percent = round(goal.actual_value * 100 / goal.target_value) if goal.target_value else 0
    await call.message.answer(
        f"🎯 {goal.title}\n\n"
        f"Месяц: {goal.period}\n"
        f"Подразделение: {target.name if target else '—'}\n"
        f"Показатель: {goal.metric}\n"
        f"План: {goal.target_value}\nФакт: {goal.actual_value}\n"
        f"Выполнение: {percent}%\nСтатус: {'завершена' if goal.status == 'completed' else 'активна'}",
        reply_markup=_keyboard([
            [
                InlineKeyboardButton(text="Изменить план", callback_data=f"admin:goal:edit:{goal.id}:target_value"),
                InlineKeyboardButton(text="Обновить факт", callback_data=f"admin:goal:edit:{goal.id}:actual_value"),
            ],
            [InlineKeyboardButton(text="Изменить название", callback_data=f"admin:goal:edit:{goal.id}:title")],
            [InlineKeyboardButton(text="✅ Завершить", callback_data=f"admin:goal:complete:{goal.id}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin:goal:delete:{goal.id}")],
            [InlineKeyboardButton(text="← К целям", callback_data="admin:goals")],
        ]),
    )


@router.callback_query(F.data.startswith("admin:goal:edit:"))
async def goal_edit_start(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, goal_id, field = call.data.split(":")
    await state.update_data(goal_edit_id=int(goal_id), goal_edit_field=field)
    await state.set_state(GoalStates.edit_value)
    await call.message.answer("Отправьте новое значение", reply_markup=_back(f"admin:goal:view:{goal_id}"))


@router.message(GoalStates.edit_value)
async def goal_edit_save(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    goal = await session.get(MonthlyGoal, data["goal_edit_id"])
    if goal is None:
        await state.clear()
        return
    field = data["goal_edit_field"]
    if field in {"target_value", "actual_value"}:
        try:
            value = int((message.text or "").strip())
            if value < 0 or (field == "target_value" and value == 0):
                raise ValueError
        except ValueError:
            await message.answer("Введите целое неотрицательное число")
            return
    else:
        value = clean_text(message.text or "", 255)
        if not value:
            await message.answer("Значение не должно быть пустым")
            return
    setattr(goal, field, value)
    goal.updated_by = user.id
    await state.clear()
    await message.answer("Изменение сохранено", reply_markup=_keyboard([[InlineKeyboardButton(text="Открыть цель", callback_data=f"admin:goal:view:{goal.id}")]]))


@router.callback_query(F.data.regexp(r"^admin:goal:(complete|delete):\d+$"))
async def goal_status(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    action, goal_id = call.data.split(":")[-2:]
    goal = await session.get(MonthlyGoal, int(goal_id))
    if goal:
        goal.status = "completed" if action == "complete" else "deleted"
        goal.updated_by = user.id
    await call.message.answer("Готово", reply_markup=_back("admin:goals"))


def _contacts_keyboard(items: list[OrganizationContact]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="➕ Добавить контакт", callback_data="admin:contacts:new")]]
    for item in items[:25]:
        label = item.organization or item.contact_name or f"Контакт #{item.id}"
        rows.append([InlineKeyboardButton(text=label[:55], callback_data=f"admin:contact:view:{item.id}")])
    rows.append([InlineKeyboardButton(text="← Управление", callback_data="admin:menu:system")])
    return _keyboard(rows)


@router.callback_query(F.data == "admin:contacts")
async def contacts_menu(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    items = (
        await session.scalars(
            select(OrganizationContact)
            .where(OrganizationContact.is_active.is_(True))
            .order_by(OrganizationContact.organization, OrganizationContact.contact_name)
        )
    ).all()
    await call.message.answer(
        "🤝 База коллег и организаций\n\nЛюбое поле можно пропустить символом —",
        reply_markup=_contacts_keyboard(list(items)),
    )


CONTACT_STEPS = (
    ("organization", ContactStates.organization, "Организация"),
    ("contact_name", ContactStates.contact_name, "Контактное лицо"),
    ("position_primary", ContactStates.position_primary, "Должность 1"),
    ("position_secondary", ContactStates.position_secondary, "Должность 2"),
    ("email", ContactStates.email, "Почта"),
    ("phone", ContactStates.phone, "Телефон"),
    ("notes", ContactStates.notes, "Комментарий"),
)


@router.callback_query(F.data == "admin:contacts:new")
async def contact_new(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    await state.set_state(ContactStates.organization)
    await call.message.answer("Организация\n\nОтправьте — чтобы пропустить", reply_markup=_back("admin:contacts"))


async def _contact_step(message: Message, state: FSMContext, key: str, next_state, prompt: str) -> None:
    value = clean_text(message.text or "", 1500)
    await state.update_data(**{key: None if value in {"", "—", "-"} else value})
    await state.set_state(next_state)
    await message.answer(f"{prompt}\n\nОтправьте — чтобы пропустить")


@router.message(ContactStates.organization)
async def contact_org(message: Message, state: FSMContext) -> None:
    await _contact_step(message, state, "organization", ContactStates.contact_name, "Контактное лицо")


@router.message(ContactStates.contact_name)
async def contact_name(message: Message, state: FSMContext) -> None:
    await _contact_step(message, state, "contact_name", ContactStates.position_primary, "Должность 1")


@router.message(ContactStates.position_primary)
async def contact_position1(message: Message, state: FSMContext) -> None:
    await _contact_step(message, state, "position_primary", ContactStates.position_secondary, "Должность 2")


@router.message(ContactStates.position_secondary)
async def contact_position2(message: Message, state: FSMContext) -> None:
    await _contact_step(message, state, "position_secondary", ContactStates.email, "Почта")


@router.message(ContactStates.email)
async def contact_email(message: Message, state: FSMContext) -> None:
    await _contact_step(message, state, "email", ContactStates.phone, "Телефон")


@router.message(ContactStates.phone)
async def contact_phone(message: Message, state: FSMContext) -> None:
    await _contact_step(message, state, "phone", ContactStates.notes, "Комментарий")


@router.message(ContactStates.notes)
async def contact_finish(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    value = clean_text(message.text or "", 1500)
    await state.update_data(notes=None if value in {"", "—", "-"} else value)
    data = await state.get_data()
    item = OrganizationContact(
        organization=data.get("organization"),
        contact_name=data.get("contact_name"),
        position_primary=data.get("position_primary"),
        position_secondary=data.get("position_secondary"),
        email=data.get("email"),
        phone=data.get("phone"),
        notes=data.get("notes"),
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(item)
    await session.flush()
    await state.clear()
    await message.answer("Контакт сохранён", reply_markup=_keyboard([[InlineKeyboardButton(text="Открыть", callback_data=f"admin:contact:view:{item.id}")]]))


@router.callback_query(F.data.startswith("admin:contact:view:"))
async def contact_view(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    item = await session.get(OrganizationContact, int(call.data.rsplit(":", 1)[-1]))
    if not item or not item.is_active:
        await call.message.answer("Контакт не найден")
        return
    await call.message.answer(
        f"🤝 {item.organization or 'Организация не указана'}\n\n"
        f"Контакт: {item.contact_name or '—'}\n"
        f"Должность 1: {item.position_primary or '—'}\n"
        f"Должность 2: {item.position_secondary or '—'}\n"
        f"Почта: {item.email or '—'}\n"
        f"Телефон: {item.phone or '—'}\n"
        f"Комментарий: {item.notes or '—'}",
        reply_markup=_keyboard([
            [InlineKeyboardButton(text="✏️ Заполнить заново", callback_data=f"admin:contact:redo:{item.id}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin:contact:delete:{item.id}")],
            [InlineKeyboardButton(text="← К базе", callback_data="admin:contacts")],
        ]),
    )


@router.callback_query(F.data.startswith("admin:contact:redo:"))
async def contact_redo(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    item = await session.get(OrganizationContact, int(call.data.rsplit(":", 1)[-1]))
    if item:
        item.is_active = False
        item.updated_by = user.id
    await state.clear()
    await state.set_state(ContactStates.organization)
    await call.message.answer("Введите обновлённые данные.\n\nОрганизация\nОтправьте — чтобы пропустить")


@router.callback_query(F.data.startswith("admin:contact:delete:"))
async def contact_delete(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    item = await session.get(OrganizationContact, int(call.data.rsplit(":", 1)[-1]))
    if item:
        item.is_active = False
        item.updated_by = user.id
    await call.message.answer("Контакт удалён", reply_markup=_back("admin:contacts"))


@router.callback_query(F.data == "admin:content")
async def content_menu(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    departments = (await session.scalars(select(Department).order_by(Department.name))).all()
    directions = (await session.scalars(select(Direction).order_by(Direction.name))).all()
    rows = [[InlineKeyboardButton(text=f"🏛 {x.name}", callback_data=f"admin:content:department:{x.id}")] for x in departments]
    rows += [[InlineKeyboardButton(text=f"🧭 {x.name}", callback_data=f"admin:content:direction:{x.id}")] for x in directions]
    rows.append([InlineKeyboardButton(text="← Управление", callback_data="admin:menu:system")])
    await call.message.answer(
        "✏️ Редактор структуры\n\nВыберите департамент или направление, чтобы изменить описание прямо из Telegram",
        reply_markup=_keyboard(rows),
    )


@router.callback_query(F.data.regexp(r"^admin:content:(department|direction):\d+$"))
async def content_edit_start(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    kind, item_id = call.data.split(":")[-2:]
    model = Department if kind == "department" else Direction
    item = await session.get(model, int(item_id))
    if not item:
        return
    await state.update_data(content_kind=kind, content_id=item.id)
    await state.set_state(ContentEditStates.description)
    await call.message.answer(
        f"{item.name}\n\nТекущее описание:\n{item.description or 'не заполнено'}\n\nОтправьте новое описание",
        reply_markup=_back("admin:content"),
    )


@router.message(ContentEditStates.description)
async def content_edit_save(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    value = clean_text(message.text or "", 3000)
    if not value:
        await message.answer("Описание не должно быть пустым")
        return
    data = await state.get_data()
    model = Department if data["content_kind"] == "department" else Direction
    item = await session.get(model, data["content_id"])
    if item:
        item.description = value
    await state.clear()
    await message.answer("Описание обновлено и будет показано участникам", reply_markup=_back("admin:content"))


@router.callback_query(F.data.startswith("admin:office:edit:"))
async def office_edit_start(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, _, office_id, field = call.data.split(":")
    await state.update_data(office_edit_id=int(office_id), office_edit_field=field)
    await state.set_state(OfficeEditStates.value)
    await call.message.answer("Отправьте новое значение")


@router.message(OfficeEditStates.value)
async def office_edit_save(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    value = clean_text(message.text or "", 1000)
    if not value:
        await message.answer("Значение не должно быть пустым")
        return
    data = await state.get_data()
    office = await session.get(Office, data["office_edit_id"])
    if office:
        setattr(office, data["office_edit_field"], value)
    await state.clear()
    await message.answer("Должность обновлена", reply_markup=_keyboard([[InlineKeyboardButton(text="Открыть должность", callback_data=f"admin:office:view:{office.id}")]]))


@router.callback_query(F.data.startswith("admin:office:disable:"))
async def office_disable(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    office = await session.get(Office, int(call.data.rsplit(":", 1)[-1]))
    if office:
        office.is_active = False
    await call.message.answer("Должность удалена из активного списка", reply_markup=_back("admin:offices"))


CHAT_LABELS = {
    "era_channel": "Канал ЭРА",
    "general": "Общий чат",
    "internal": "Внутренние связи",
    "external": "Внешние связи",
    "leaders": "Лидерский чат",
}


@router.callback_query(F.data == "admin:chat_broadcast")
async def chat_broadcast_start(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    await state.update_data(chat_targets=[])
    await _show_chat_targets(call.message, [])


async def _show_chat_targets(message: Message, selected: list[str]) -> None:
    rows = []
    for key, label in CHAT_LABELS.items():
        mark = "✅ " if key in selected else ""
        rows.append([InlineKeyboardButton(text=mark + label, callback_data=f"admin:chat_broadcast:toggle:{key}")])
    rows.append([InlineKeyboardButton(text="Продолжить", callback_data="admin:chat_broadcast:text")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="admin:menu:communications")])
    await message.answer("Выберите один или несколько чатов", reply_markup=_keyboard(rows))


@router.callback_query(F.data.startswith("admin:chat_broadcast:toggle:"))
async def chat_broadcast_toggle(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    key = call.data.rsplit(":", 1)[-1]
    data = await state.get_data()
    selected = list(data.get("chat_targets", []))
    if key in selected:
        selected.remove(key)
    else:
        selected.append(key)
    await state.update_data(chat_targets=selected)
    await _show_chat_targets(call.message, selected)


@router.callback_query(F.data == "admin:chat_broadcast:text")
async def chat_broadcast_text_start(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    selected = (await state.get_data()).get("chat_targets", [])
    if not selected:
        await call.message.answer("Выберите хотя бы один чат")
        return
    await state.set_state(ChatBroadcastStates.text)
    await call.message.answer("Отправьте сообщение для выбранных чатов")


@router.message(ChatBroadcastStates.text)
async def chat_broadcast_text(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 4000)
    if not value:
        await message.answer("Сообщение не должно быть пустым")
        return
    await state.update_data(chat_broadcast_text=value)
    await state.set_state(ChatBroadcastStates.confirm)
    data = await state.get_data()
    labels = ", ".join(CHAT_LABELS[x] for x in data["chat_targets"])
    await message.answer(
        f"Проверьте сообщение\n\nКуда: {labels}\n\n{value}",
        reply_markup=_keyboard([
            [InlineKeyboardButton(text="✅ Отправить", callback_data="admin:chat_broadcast:send")],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:menu:communications")],
        ]),
    )


@router.callback_query(ChatBroadcastStates.confirm, F.data == "admin:chat_broadcast:send")
async def chat_broadcast_send(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext, bot: Bot
) -> None:
    if not await _guard(call, user, settings):
        return
    data = await state.get_data()
    id_fields = {
        "era_channel": "era_channel_id",
        "general": "general_chat_id",
        "internal": "internal_department_chat_id",
        "external": "external_department_chat_id",
        "leaders": "leaders_chat_id",
    }
    sent, missing, failed = [], [], []
    for key in data["chat_targets"]:
        chat_id = getattr(settings, id_fields[key], None)
        if not chat_id:
            missing.append(CHAT_LABELS[key])
            continue
        try:
            await bot.send_message(chat_id, data["chat_broadcast_text"])
            sent.append(CHAT_LABELS[key])
        except Exception:
            failed.append(CHAT_LABELS[key])
    await state.clear()
    await call.message.answer(
        "Рассылка завершена\n\n"
        f"Отправлено: {', '.join(sent) or '—'}\n"
        f"Не привязаны: {', '.join(missing) or '—'}\n"
        f"Ошибка отправки: {', '.join(failed) or '—'}",
        reply_markup=_back("admin:menu:communications"),
    )
