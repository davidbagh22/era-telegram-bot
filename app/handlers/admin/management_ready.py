from __future__ import annotations

from aiogram import F, Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.management_models import MonthlyGoal, OrganizationContact
from app.database.models import Department, User
from app.keyboards.participant import open_app_button
from app.services.admin_analytics_service import EXCEL_SECTION_MAP, build_analytics_payload
from app.services.admin_broadcast_service import BroadcastError, send_chat_broadcast
from app.services.admin_contacts_service import ContactError, archive_contact, create_contact
from app.services.admin_goals_service import GoalError, create_goal, decide_goal
from app.services.admin_structure_service import StructureError, update_department_description
from app.services.excel_service import build_analytics_workbook
from app.services.notification_service import safe_answer_document
from app.utils import texts
from app.utils.constants import Role
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
    # /panel used to open the full bot-native admin menu tree
    # (admin_panel_keyboard()). Admin Mode in the Mini App now covers
    # everything that tree offered (see docs/SYSTEM_FLOW_MATRIX.md and the
    # 2026-08 master spec's Bot/Mini App role split) — this command is kept
    # live only as a compatibility redirect, not a duplicate interface.
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(texts.ADMIN_PANEL_MOVED, reply_markup=open_app_button(settings.effective_miniapp_url))


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


@router.callback_query(F.data == "admin:analytics")
async def analytics(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    data = await build_analytics_payload(session)
    text = (
        "📊 Аналитика ЭРА\n\n"
        f"Участников в базе: {data.summary['total_users']}\n"
        f"Одобрены: {data.summary['approved_users']}\n"
        f"Новые заявки: {data.summary['pending_users']}\n"
        f"Мероприятий: {data.summary['events']}\n"
        f"Проектов: {data.summary['projects']}\n"
        f"Организаций в базе: {data.summary['contacts']}\n"
        f"Целей месяца: {data.summary['goals']}\n\n"
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
    data = await build_analytics_payload(session)
    content = build_analytics_workbook(
        data.users,
        data.events,
        data.projects,
        data.totals,
        department_stats=data.department_stats,
        direction_stats=data.direction_stats,
        goals=data.goals,
        contacts=data.contacts,
        sections=EXCEL_SECTION_MAP.get(section),
    )
    if not await safe_answer_document(
        call.message,
        BufferedInputFile(content, filename=f"ERA_analytics_{section}.xlsx"),
        caption="Готово. Таблица оформлена на русском и готова для работы",
    ):
        await call.message.answer("Таблица собрана, но Telegram не дал отправить файл. Попробуйте ещё раз.")


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
    try:
        await create_goal(
            session,
            title=parts[0],
            target_value=target,
            month=parts[2] if len(parts) > 2 else None,
            scope_query=parts[3] if len(parts) > 3 else None,
            timezone=settings.timezone,
            updated_by=user.id if user else None,
        )
    except GoalError:
        await message.answer("Не получилось сохранить цель. Проверьте план — он должен быть больше нуля")
        return
    await state.clear()
    await message.answer("Цель добавлена ✅")


@router.callback_query(F.data.regexp(r"^admin:goal:(inc|done|del):\d+$"))
async def goal_action(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    _, _, raw_action, raw_id = call.data.split(":")
    action = "delete" if raw_action == "del" else raw_action
    try:
        await decide_goal(session, int(raw_id), action, user.id if user else None)
    except GoalError:
        await call.message.answer("Цель не найдена")
        return
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
    try:
        await create_contact(
            session,
            organization_name=_empty(parts[0]) or "Без названия",
            contact_name=_empty(parts[1]),
            position=_empty(parts[2]),
            second_contact_name=_empty(parts[3]),
            second_position=_empty(parts[4]),
            email=_empty(parts[5]),
            phone=_empty(parts[6]),
            notes=_empty(parts[7]),
            created_by=user.id if user else None,
        )
    except ContactError:
        await message.answer("Нужно указать хотя бы название организации")
        return
    await state.clear()
    await message.answer("Контакт добавлен ✅")


@router.callback_query(F.data.startswith("admin:contact:del:"))
async def contact_delete(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    try:
        await archive_contact(session, int(call.data.rsplit(":", 1)[-1]))
    except ContactError:
        pass
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
    try:
        await send_chat_broadcast(bot, settings, session, chat_key=key, text=text, actor_id=user.id if user else None)
    except BroadcastError as exc:
        message = (
            "ID этого чата ещё не привязан. Используйте /bind в нужном чате или настройки"
            if exc.code == "chat_not_bound"
            else "Telegram не дал отправить сообщение. Проверьте, что бот админ в этом чате"
        )
        await call.message.answer(message)
        return
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
    try:
        await update_department_description(session, int(data["department_id"]), clean_text(message.text or "", 3000))
    except StructureError:
        await state.clear()
        return
    await state.clear()
    await message.answer("Описание обновлено ✅")
