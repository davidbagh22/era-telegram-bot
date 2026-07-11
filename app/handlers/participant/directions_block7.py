from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Department, Direction, User, UserDepartment, UserDirection
from app.services.audit_service import audit
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="participant_directions_block7")

DEPARTMENT_KEYS = {
    "internal": "Внутренние связи",
    "external": "Внешние связи",
}


def _chat_url(settings: Settings, key: str, department: Department | None = None) -> str | None:
    if department and department.chat_url:
        return department.chat_url
    if key == "internal":
        return settings.internal_department_chat_url
    if key == "external":
        return settings.external_department_chat_url
    return None


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return False
    if user.is_blocked or user.is_archived:
        await call.message.answer(texts.BLOCKED)
        return False
    return True


def _selected_text(user: User) -> str:
    departments = ", ".join(item.department.name for item in user.departments) or "пока не выбран"
    directions = ", ".join(item.direction.name for item in user.directions) or "пока не выбрано"
    return f"Ваш департамент: {departments}\nВаше направление: {directions}"


def _directions_menu_keyboard(settings: Settings) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🌿 Внутренние связи", callback_data="department:view:internal")],
        [InlineKeyboardButton(text="🌍 Внешние связи", callback_data="department:view:external")],
    ]
    if settings.internal_department_chat_url:
        rows.append([InlineKeyboardButton(text="💬 Чат внутренних связей", url=settings.internal_department_chat_url)])
    if settings.external_department_chat_url:
        rows.append([InlineKeyboardButton(text="💬 Чат внешних связей", url=settings.external_department_chat_url)])
    rows.append([InlineKeyboardButton(text="← Мои данные", callback_data="cabinet:profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _department_keyboard(key: str, department: Department | None, directions: list[Direction], settings: Settings) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"✅ Выбрать: {direction.name}", callback_data=f"department:select_direction:{direction.id}")]
        for direction in directions
    ]
    chat_url = _chat_url(settings, key, department)
    if chat_url:
        rows.append([InlineKeyboardButton(text="💬 Перейти в чат департамента", url=chat_url)])
    rows.extend(
        [
            [InlineKeyboardButton(text="📌 Все департаменты", callback_data="cabinet:departments")],
            [InlineKeyboardButton(text="← Мои данные", callback_data="cabinet:profile")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _get_department(session: AsyncSession, key: str) -> Department | None:
    name = DEPARTMENT_KEYS.get(key)
    if not name:
        return None
    department = await session.scalar(select(Department).where(Department.name == name))
    if department:
        return department
    return await session.scalar(select(Department).where(Department.name.ilike(f"%{name.split()[0]}%")))


@router.callback_query(F.data.in_({"cabinet:departments", "departments:menu"}))
async def directions_menu(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
) -> None:
    if not await _guard(call, user):
        return
    await call.message.answer(
        "🧩 Департаменты и направления\n\n"
        f"{_selected_text(user)}\n\n"
        "Выберите, куда Вам ближе сейчас. Можно изменить выбор позже — просто выберите другое направление",
        reply_markup=_directions_menu_keyboard(settings),
    )


@router.callback_query(F.data.startswith("department:view:"))
async def department_view(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user):
        return
    key = call.data.rsplit(":", 1)[-1]
    department = await _get_department(session, key)
    if not department:
        await call.message.answer("Департамент пока не найден в базе. Сообщите администратору ЭРА")
        return
    directions = (
        await session.scalars(
            select(Direction).where(Direction.department_id == department.id).order_by(Direction.name)
        )
    ).all()
    if not directions:
        await call.message.answer("У этого департамента пока нет направлений. Администратор сможет добавить их в структуре")
        return
    direction_lines = "\n".join(
        f"• {direction.name}" + (f" — {direction.description}" if direction.description else "")
        for direction in directions
    )
    await call.message.answer(
        f"{department.name}\n\n"
        f"{department.description or 'Здесь собраны направления, где можно включиться в работу ЭРА'}\n\n"
        f"Направления:\n{direction_lines}\n\n"
        "Нажмите на направление, чтобы сохранить его в своём профиле",
        reply_markup=_department_keyboard(key, department, directions, settings),
    )


@router.callback_query(F.data.regexp(r"^department:select_direction:\d+$"))
async def select_direction(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user):
        return
    direction = await session.get(Direction, int(call.data.rsplit(":", 1)[-1]))
    if not direction:
        await call.message.answer("Направление не найдено")
        return
    department = await session.get(Department, direction.department_id)
    department_link = await session.scalar(
        select(UserDepartment).where(
            UserDepartment.user_id == user.id,
            UserDepartment.department_id == direction.department_id,
        )
    )
    if department_link:
        department_link.status = "interested"
    else:
        session.add(
            UserDepartment(
                user_id=user.id,
                department_id=direction.department_id,
                status="interested",
            )
        )
    direction_link = await session.scalar(
        select(UserDirection).where(
            UserDirection.user_id == user.id,
            UserDirection.direction_id == direction.id,
        )
    )
    if direction_link:
        direction_link.status = "interested"
    else:
        session.add(
            UserDirection(
                user_id=user.id,
                direction_id=direction.id,
                status="interested",
            )
        )
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="user.direction_selected",
        entity_type="direction",
        entity_id=direction.id,
        new_value={"department_id": direction.department_id, "direction_id": direction.id},
    )
    key = "internal" if department and "внут" in department.name.lower() else "external"
    chat_url = _chat_url(settings, key, department)
    rows = []
    if chat_url:
        rows.append([InlineKeyboardButton(text="💬 Перейти в чат департамента", url=chat_url)])
    rows.extend(
        [
            [InlineKeyboardButton(text="🧩 Выбрать ещё направление", callback_data="cabinet:departments")],
            [InlineKeyboardButton(text="← Мои данные", callback_data="cabinet:profile")],
        ]
    )
    await call.message.answer(
        f"Готово ✅\n\n"
        f"Вы выбрали направление: {direction.name}\n"
        f"Департамент: {department.name if department else 'не указан'}\n\n"
        "Выбор уже сохранён в профиле. Если захотите поменять или добавить ещё одно направление — вернитесь в этот раздел",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "department:chats")
async def department_chats(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    if not await _guard(call, user):
        return
    rows = []
    if settings.internal_department_chat_url:
        rows.append([InlineKeyboardButton(text="🌿 Чат внутренних связей", url=settings.internal_department_chat_url)])
    if settings.external_department_chat_url:
        rows.append([InlineKeyboardButton(text="🌍 Чат внешних связей", url=settings.external_department_chat_url)])
    if settings.general_chat_url:
        rows.append([InlineKeyboardButton(text="💬 Общий чат ЭРА", url=settings.general_chat_url)])
    rows.append([InlineKeyboardButton(text="← Департаменты", callback_data="cabinet:departments")])
    await call.message.answer("Чаты ЭРА\n\nВыберите нужный чат", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
