from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.management_models import MonthlyGoal, OrganizationContact
from app.database.models import Department, Direction, Event, PointTransaction, Project, User, UserDepartment, UserDirection
from app.keyboards.admin import admin_panel_keyboard
from app.services.audit_service import audit
from app.services.excel_service import build_analytics_workbook
from app.utils import texts
from app.utils.constants import ApplicationStatus, Role
from app.utils.validators import clean_text

router = Router(name="admin_management_ready")


class AdminReadyStates(StatesGroup):
    goal_text = State()
    contact_text = State()
    chat_text = State()
    department_text = State()


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked and not user.is_archived)
        or (user and not user.is_blocked and not user.is_archived and any(grant.is_active for grant in (user.permission_grants or [])))
    )


async def _guard(event: Message | CallbackQuery, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        target = event.message
        telegram_id = event.from_user.id
    else:
        target = event
        telegram_id = event.from_user.id
    if not _is_admin(user, settings, telegram_id):
        await target.answer(texts.NO_ACCESS)
        return False
    return True


def _system_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Аналитика и Excel", callback_data="admin:analytics")],
        [InlineKeyboardButton(text="🎯 Ежемесячные цели", callback_data="admin:goals")],
        [InlineKeyboardButton(text="🤝 База организаций", callback_data="admin:contacts")],
        [InlineKeyboardButton(text="🏛 Редактор структуры", callback_data="admin:structure")],
        [InlineKeyboardButton(text="👥 Должности и права", callback_data="admin:offices")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin:settings")],
        [InlineKeyboardButton(text="🧹 Очистка тестовых данных", callback_data="admin:maintenance")],
        [InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")],
    ])


def _communications_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Вопросы пользователей", callback_data="admin:questions")],
        [InlineKeyboardButton(text="📨 Рассылка в личные сообщения", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="📣 Сообщение в выбранные чаты", callback_data="admin:chat_broadcast")],
        [InlineKeyboardButton(text="👋 Приветствия в чатах", callback_data="admin:greetings")],
        [InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")],
    ])


@router.message(Command("panel"))
async def panel_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(texts.ADMIN_PANEL, reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin:menu:system")
async def system_menu(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "📊 Управление\n\nЗдесь находятся аналитика, Excel, цели месяца, база организаций, структура и технические настройки",
        reply_markup=_system_keyboard(),
    )


@router.callback_query(F.data == "admin:menu:communications")
async def communications_menu(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    if not await _guard(call, user, settings):
        return
    await call.message.answer(
        "💬 Общение\n\nВыберите, куда и как нужно отправить сообщение",
        reply_markup=_communications_keyboard(),
    )


async def _analytics_payload(session: AsyncSession) -> dict:
    users = (await session.scalars(select(User).where(User.is_archived.is_(False)).order_by(User.first_name))).all()
    events = (await session.scalars(select(Event).order_by(Event.event_date.desc(), Event.event_time).limit(500))).all()
    projects = (await session.scalars(select(Project).order_by(Project.created_at.desc()).limit(500))).all()
    totals = dict((await session.execute(select(PointTransaction.user_id, func.coalesce(func.sum(PointTransaction.points), 0)).group_by(PointTransaction.user_id))).all())

    dep_rows = (await session.execute(
        select(Department.id, Department.name, func.count(UserDepartment.id))
        .join(UserDepartment, Department.id == UserDepartment.department_id, isouter=True)
        .group_by(Department.id, Department.name)
        .order_by(Department.name)
    )).all()
    dir_rows = (await session.execute(
        select(Department.name, Direction.id, Direction.name, func.count(UserDirection.id))
        .join(Direction, Direction.department_id == Department.id)
        .join(UserDirection, UserDirection.direction_id == Direction.id, isouter=True)
        .group_by(Department.name, Direction.id, Direction.name)
        .order_by(Department.name, Direction.name)
    )).all()
    goals = (await session.scalars(select(MonthlyGoal).where(MonthlyGoal.status != "deleted").order_by(MonthlyGoal.month.desc(), MonthlyGoal.created_at.desc()).limit(200))).all()
    contacts = (await session.scalars(select(OrganizationContact).where(OrganizationContact.is_active.is_(True)).order_by(OrganizationContact.organization_name))).all()

    goals_by_department = {row[0]: {"active": 0, "done": 0} for row in dep_rows}
    for goal in goals:
        if goal.scope_type == "department" and goal.scope_id in goals_by_department:
            key = "done" if goal.status == "done" else "active"
            goals_by_department[goal.scope_id][key] += 1

    department_stats = [
        {
            "id": dep_id,
            "name": name,
            "members": members,
            "active_goals": goals_by_department.get(dep_id, {}).get("active", 0),
            "done_goals": goals_by_department.get(dep_id, {}).get("done", 0),
        }
        for dep_id, name, members in dep_rows
    ]
    direction_stats = [
        {"department": dep_name, "id": direction_id, "name": direction_name, "members": members}
        for dep_name, direction_id, direction_name, members in dir_rows
    ]
    goal_rows = []
    for goal in goals:
        scope_name = "Вся организация"
        if goal.scope_type == "department" and goal.scope_id:
            found = next((item["name"] for item in department_stats if item["id"] == goal.scope_id), None)
            scope_name = found or scope_name
        elif goal.scope_type == "direction" and goal.scope_id:
            found = next((item["name"] for item in direction_stats if item["id"] == goal.scope_id), None)
            scope_name = found or scope_name
        goal_rows.append({
            "month": goal.month,
            "scope_type": goal.scope_type,
            "scope_name": scope_name,
            "title": goal.title,
            "target_value": goal.target_value,
            "current_value": goal.current_value,
            "status": goal.status,
            "due_date": goal.due_date,
        })
    return {
        "users": users,
        "events": events,
        "projects": projects,
        "totals": totals,
        "department_stats": department_stats,
        "direction_stats": direction_stats,
        "goals": goal_rows,
        "contacts": contacts,
    }


@router.callback_query(F.data == "admin:analytics")
async def analytics(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    data = await _analytics_payload(session)
    approved = sum(1 for item in data["users"] if item.application_status == ApplicationStatus.APPROVED)
    pending = sum(1 for item in data["users"] if item.application_status == ApplicationStatus.PENDING)
    text = (
        "📊 Аналитика ЭРА\n\n"
        f"Участников в базе: {len(data['users'])}\n"
        f"Одобрены: {approved}\n"
        f"Новые заявки: {pending}\n"
        f"Мероприятий: {len(data['events'])}\n"
        f"Проектов: {len(data['projects'])}\n"
        f"Организаций в базе: {len(data['contacts'])}\n"
        f"Целей месяца: {len(data['goals'])}\n\n"
        "Можно скачать всю книгу или только нужный раздел"
    )
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📘 Скачать всё", callback_data="admin:analytics:excel:all")],
        [InlineKeyboardButton(text="👥 Участники", callback_data="admin:analytics:excel:users"), InlineKeyboardButton(text="🏛 Департаменты", callback_data="admin:analytics:excel:departments")],
        [InlineKeyboardButton(text="📅 Мероприятия", callback_data="admin:analytics:excel:events"), InlineKeyboardButton(text="💡 Проекты", callback_data="admin:analytics:excel:projects")],
        [InlineKeyboardButton(text="🎯 Цели месяца", callback_data="admin:goals"), InlineKeyboardButton(text="🤝 Организации", callback_data="admin:contacts")],
        [InlineKeyboardButton(text="← Управление", callback_data="admin:menu:system")],
    ]))


@router.callback_query(F.data.in_({"admin:analytics:excel", "admin:analytics:excel:all", "admin:analytics:excel:users", "admin:analytics:excel:departments", "admin:analytics:excel:events", "admin:analytics:excel:projects"}))
async def analytics_excel(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    section = call.data.rsplit(":", 1)[-1] if call.data.count(":") >= 3 else "all"
    section_map = {
        "users": {"summary", "users"},
        "departments": {"summary", "departments", "directions", "goals"},
        "events": {"summary", "events"},
        "projects": {"summary", "projects"},
        "all": None,
    }
    data = await _analytics_payload(session)
    content = build_analytics_workbook(
        data["users"],
        data["events"],
        data["projects"],
        data["totals"],
        department_stats=data["department_stats"],
        direction_stats=data["direction_stats"],
        goals=data["goals"],
        contacts=data["contacts"],
        sections=section_map.get(section),
    )
    await call.message.answer_document(
        BufferedInputFile(content, filename=f"ERA_analytics_{section}.xlsx"),
        caption="Готово. Таблица оформлена на русском и готова для работы",
    )


@router.callback_query(F.data == "admin:goals")
async def goals_menu(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    goals = (await session.scalars(select(MonthlyGoal).where(MonthlyGoal.status != "deleted").order_by(MonthlyGoal.month.desc(), MonthlyGoal.created_at.desc()).limit(20))).all()
    lines = ["🎯 Ежемесячные цели\n"]
    rows: list[list[InlineKeyboardButton]] = []
    for goal in goals:
        lines.append(f"#{goal.id} · {goal.month} · {goal.title}\n{goal.current_value}/{goal.target_value} · {goal.status}")
        rows.append([
            InlineKeyboardButton(text=f"+1 к #{goal.id}", callback_data=f"admin:goal:inc:{goal.id}"),
            InlineKeyboardButton(text="Готово", callback_data=f"admin:goal:done:{goal.id}"),
            InlineKeyboardButton(text="Удалить", callback_data=f"admin:goal:del:{goal.id}"),
        ])
    if not goals:
        lines.append("Пока целей нет")
    rows.append([InlineKeyboardButton(text="➕ Добавить цель", callback_data="admin:goal:new")])
    rows.append([InlineKeyboardButton(text="← Управление", callback_data="admin:menu:system")])
    await call.message.answer("\n\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "admin:goal:new")
async def goal_new(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminReadyStates.goal_text)
    await call.message.answer(
        "Напишите цель одной строкой:\n\n"
        "Название | план | месяц | департамент или направление\n\n"
        "Пример:\nПровести 2 встречи медиа | 2 | 2026-07 | Медиа\n\n"
        "Можно короче: Название | план — тогда цель будет общей на текущий месяц"
    )


@router.message(AdminReadyStates.goal_text)
async def goal_save(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    parts = [clean_text(part, 255) for part in (message.text or "").split("|")]
    if len(parts) < 2 or not parts[0]:
        await message.answer("Не получилось разобрать цель. Формат: Название | план | месяц | департамент")
        return
    try:
        target = int(parts[1])
    except ValueError:
        await message.answer("План должен быть числом. Например: 3")
        return
    month = parts[2] if len(parts) > 2 and parts[2] else datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m")
    scope_type = "global"
    scope_id = None
    if len(parts) > 3 and parts[3]:
        query = parts[3].casefold()
        department = await session.scalar(select(Department).where(func.lower(Department.name).contains(query)))
        direction = await session.scalar(select(Direction).where(func.lower(Direction.name).contains(query)))
        if direction:
            scope_type, scope_id = "direction", direction.id
        elif department:
            scope_type, scope_id = "department", department.id
    session.add(MonthlyGoal(month=month, title=parts[0], target_value=target, scope_type=scope_type, scope_id=scope_id, updated_by=user.id if user else None))
    await session.flush()
    await state.clear()
    await message.answer("Цель добавлена ✅")


@router.callback_query(F.data.regexp(r"^admin:goal:(inc|done|del):\d+$"))
async def goal_action(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, action, raw_id = call.data.split(":")
    goal = await session.get(MonthlyGoal, int(raw_id))
    if not goal:
        await call.message.answer("Цель не найдена")
        return
    if action == "inc":
        goal.current_value += 1
    elif action == "done":
        goal.current_value = max(goal.current_value, goal.target_value)
        goal.status = "done"
    else:
        goal.status = "deleted"
    goal.updated_by = user.id if user else None
    await session.flush()
    await call.message.answer("Цель обновлена")


@router.callback_query(F.data == "admin:contacts")
async def contacts_menu(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    contacts = (await session.scalars(select(OrganizationContact).where(OrganizationContact.is_active.is_(True)).order_by(OrganizationContact.organization_name).limit(30))).all()
    lines = ["🤝 База организаций и коллег\n"]
    rows = []
    for contact in contacts:
        lines.append(f"#{contact.id} · {contact.organization_name}\n{contact.contact_name or 'Контакт не указан'} · {contact.position or 'должность не указана'}\n{contact.email or ''} {contact.phone or ''}".strip())
        rows.append([InlineKeyboardButton(text=f"Удалить #{contact.id}", callback_data=f"admin:contact:del:{contact.id}")])
    if not contacts:
        lines.append("Пока контактов нет")
    rows.append([InlineKeyboardButton(text="➕ Добавить организацию", callback_data="admin:contact:new")])
    rows.append([InlineKeyboardButton(text="← Управление", callback_data="admin:menu:system")])
    await call.message.answer("\n\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "admin:contact:new")
async def contact_new(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminReadyStates.contact_text)
    await call.message.answer(
        "Отправьте карточку одной строкой:\n\n"
        "Организация | контакт | должность | второй контакт | должность 2 | почта | телефон | заметка\n\n"
        "Любое поле можно пропустить знаком —"
    )


def _empty(value: str | None) -> str | None:
    value = clean_text(value or "", 500)
    return None if value in {"", "-", "—"} else value


@router.message(AdminReadyStates.contact_text)
async def contact_save(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    parts = [part.strip() for part in (message.text or "").split("|")]
    if not parts or not _empty(parts[0]):
        await message.answer("Нужно указать хотя бы название организации")
        return
    parts += [""] * (8 - len(parts))
    session.add(OrganizationContact(
        organization_name=_empty(parts[0]) or "Без названия",
        contact_name=_empty(parts[1]),
        position=_empty(parts[2]),
        second_contact_name=_empty(parts[3]),
        second_position=_empty(parts[4]),
        email=_empty(parts[5]),
        phone=_empty(parts[6]),
        notes=_empty(parts[7]),
        created_by=user.id if user else None,
    ))
    await session.flush()
    await state.clear()
    await message.answer("Контакт добавлен ✅")


@router.callback_query(F.data.startswith("admin:contact:del:"))
async def contact_delete(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    contact = await session.get(OrganizationContact, int(call.data.rsplit(":", 1)[-1]))
    if contact:
        contact.is_active = False
        await session.flush()
    await call.message.answer("Контакт скрыт из активной базы")


@router.callback_query(F.data == "admin:chat_broadcast")
async def chat_broadcast_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminReadyStates.chat_text)
    await call.message.answer("Напишите сообщение, которое бот отправит в выбранный чат")


@router.message(AdminReadyStates.chat_text)
async def chat_broadcast_choose(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    text = clean_text(message.text or "", 3500)
    if not text:
        await message.answer("Сообщение не должно быть пустым")
        return
    await state.update_data(chat_broadcast_text=text)
    await message.answer("Куда отправить?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Общий чат", callback_data="admin:chat_send:general")],
        [InlineKeyboardButton(text="Внутренние связи", callback_data="admin:chat_send:internal"), InlineKeyboardButton(text="Внешние связи", callback_data="admin:chat_send:external")],
        [InlineKeyboardButton(text="Чат лидеров", callback_data="admin:chat_send:leaders")],
        [InlineKeyboardButton(text="Отмена", callback_data="admin:menu:communications")],
    ]))


@router.callback_query(F.data.startswith("admin:chat_send:"))
async def chat_broadcast_send(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(call, user, settings):
        return
    data = await state.get_data()
    text = data.get("chat_broadcast_text")
    if not text:
        await call.message.answer("Текст не найден. Начните рассылку заново")
        return
    key = call.data.rsplit(":", 1)[-1]
    chat_ids = {
        "general": settings.general_chat_id,
        "internal": settings.internal_department_chat_id,
        "external": settings.external_department_chat_id,
        "leaders": settings.leaders_chat_id,
    }
    chat_id = chat_ids.get(key)
    if not chat_id:
        await call.message.answer("ID этого чата ещё не привязан. Используйте /bind в нужном чате или настройки")
        return
    try:
        await bot.send_message(chat_id, text)
    except TelegramAPIError:
        await call.message.answer("Telegram не дал отправить сообщение. Проверьте, что бот админ в этом чате")
        return
    await audit(session, actor_id=user.id if user else None, action="chat.broadcast_sent", entity_type="chat", entity_id=None, new_value={"chat": key})
    await state.clear()
    await call.message.answer("Сообщение отправлено ✅")


@router.callback_query(F.data == "admin:structure")
async def structure_menu(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    departments = (await session.scalars(select(Department).order_by(Department.name))).all()
    rows = [[InlineKeyboardButton(text=f"✏️ {department.name}", callback_data=f"admin:structure:dep:{department.id}")] for department in departments]
    rows.append([InlineKeyboardButton(text="← Управление", callback_data="admin:menu:system")])
    await call.message.answer("🏛 Редактор структуры\n\nВыберите департамент, чтобы изменить описание, которое видит участник", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("admin:structure:dep:"))
async def structure_department_start(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    dep_id = int(call.data.rsplit(":", 1)[-1])
    department = await session.get(Department, dep_id)
    if not department:
        return
    await state.set_state(AdminReadyStates.department_text)
    await state.update_data(department_id=dep_id)
    await call.message.answer(f"Текущее описание:\n{department.description or '—'}\n\nОтправьте новый текст описания")


@router.message(AdminReadyStates.department_text)
async def structure_department_save(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    department = await session.get(Department, int(data["department_id"]))
    if not department:
        await state.clear()
        return
    department.description = clean_text(message.text or "", 3000)
    await session.flush()
    await state.clear()
    await message.answer("Описание обновлено ✅")
