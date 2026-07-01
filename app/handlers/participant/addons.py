from aiogram import F, Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Badge,
    Department,
    Direction,
    PointTransaction,
    PortfolioItem,
    User,
    UserBadge,
    UserDepartment,
    UserDirection,
)
from app.keyboards.common import back_keyboard
from app.utils import texts
from app.utils.constants import ApplicationStatus
from app.utils.telegram import send_long_text

router = Router(name="participant_addons")


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return False
    if user.is_blocked or user.is_archived:
        await call.message.answer(texts.BLOCKED)
        return False
    return True


def _tg(user: User) -> str:
    return f"@{user.username}" if user.username else str(user.telegram_id)


async def _user_badges(session: AsyncSession, user_id: int) -> list[tuple[UserBadge, Badge]]:
    return list(
        (
            await session.execute(
                select(UserBadge, Badge)
                .join(Badge, Badge.id == UserBadge.badge_id)
                .where(UserBadge.user_id == user_id)
                .order_by(UserBadge.created_at.desc())
            )
        ).all()
    )


@router.callback_query(F.data == "cabinet:profile")
async def profile_with_badges(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    departments = ", ".join(item.department.name for item in user.departments) or "не выбраны"
    directions = ", ".join(item.direction.name for item in user.directions) or "не выбраны"
    badges = await _user_badges(session, user.id)
    badge_line = ", ".join(badge.name for _, badge in badges) or "пока нет"
    points = int(
        await session.scalar(
            select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                PointTransaction.user_id == user.id
            )
        )
        or 0
    )
    await call.message.answer(
        f"👤 {user.first_name} {user.last_name or ''}\n\n"
        f"Возраст: {user.age or 'не указан'}\n"
        f"Город: {user.city or 'не указан'}\n"
        f"Телефон: {user.phone or 'не указан'}\n"
        f"Telegram: {_tg(user)}\n"
        f"Email: {user.email or 'не указан'}\n\n"
        f"Департаменты: {departments}\n"
        f"Направления: {directions}\n\n"
        f"Баллы: {points}\n"
        f"Знаки: {badge_line}",
        reply_markup=back_keyboard("cabinet:open"),
    )


@router.callback_query(F.data.in_({"cabinet:achievements", "cabinet:points", "cabinet:journey"}))
async def achievements(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    total = int(
        await session.scalar(
            select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                PointTransaction.user_id == user.id
            )
        )
        or 0
    )
    point_rows = (
        await session.scalars(
            select(PointTransaction)
            .where(PointTransaction.user_id == user.id)
            .order_by(desc(PointTransaction.created_at))
            .limit(10)
        )
    ).all()
    badges = await _user_badges(session, user.id)
    badge_lines = [f"• {badge.name} — {award.reason}" for award, badge in badges]
    point_lines = [f"• {item.points:+d} — {item.reason}" for item in point_rows]
    await send_long_text(
        call.message,
        "🏆 Мои достижения\n\n"
        f"Баланс: {total} баллов\n\n"
        "Знаки:\n"
        + ("\n".join(badge_lines) if badge_lines else "пока нет")
        + "\n\nИстория баллов:\n"
        + ("\n".join(point_lines) if point_lines else "пока нет"),
        reply_markup=back_keyboard("cabinet:open"),
    )


@router.callback_query(F.data == "cabinet:direction:add")
async def direction_add_menu(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    selected = {item.direction_id for item in user.directions}
    directions = (await session.scalars(select(Direction).order_by(Direction.department_id, Direction.name))).all()
    rows = []
    for direction in directions:
        if direction.id in selected:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{direction.name}",
                    callback_data=f"cabinet:direction:select:{direction.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")])
    await call.message.answer(
        "Выберите новое направление, в котором хотите развиваться.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("cabinet:direction:select:"))
async def direction_select(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user):
        return
    direction = await session.get(Direction, int(call.data.rsplit(":", 1)[-1]))
    if direction is None:
        await call.message.answer("Направление не найдено")
        return
    existing_direction = await session.scalar(
        select(UserDirection).where(
            UserDirection.user_id == user.id,
            UserDirection.direction_id == direction.id,
        )
    )
    if existing_direction is None:
        session.add(UserDirection(user_id=user.id, direction_id=direction.id, status="interested"))
    existing_department = await session.scalar(
        select(UserDepartment).where(
            UserDepartment.user_id == user.id,
            UserDepartment.department_id == direction.department_id,
        )
    )
    if existing_department is None:
        session.add(UserDepartment(user_id=user.id, department_id=direction.department_id, status="interested"))
    await call.message.answer(
        f"Готово. Вы выбрали направление: {direction.name}",
        reply_markup=back_keyboard("cabinet:open"),
    )
    department = await session.get(Department, direction.department_id)
    leader_id = direction.leader_id or (department.leader_id if department else None)
    if leader_id:
        leader = await session.get(User, leader_id)
        if leader and not leader.is_blocked:
            await bot.send_message(
                leader.telegram_id,
                "Новый участник выбрал Ваше направление\n\n"
                f"Направление: {direction.name}\n"
                f"Участник: {user.first_name} {user.last_name or ''}\n"
                f"Возраст: {user.age or 'не указан'}\n"
                f"Город: {user.city or 'не указан'}\n"
                f"Телефон: {user.phone or 'не указан'}\n"
                f"Telegram: {_tg(user)}\n"
                f"Email: {user.email or 'не указан'}",
            )


@router.callback_query(F.data == "portfolio:view")
async def portfolio_view(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    if not await _guard(call, user):
        return
    items = (
        await session.scalars(
            select(PortfolioItem)
            .where(
                PortfolioItem.user_id == user.id,
                PortfolioItem.status.in_(["verified", "pending"]),
            )
            .order_by(desc(PortfolioItem.created_at))
        )
    ).all()
    if not items:
        await call.message.answer("Портфолио пока пустое.", reply_markup=back_keyboard("cabinet:portfolio"))
        return
    lines = []
    for item in items:
        status = "на проверке" if item.status == "pending" else "подтверждено"
        marker = "📎" if item.file_id else "•"
        lines.append(f"{marker} {item.title} — {status}\n{item.description or item.item_type}")
    await send_long_text(
        call.message,
        "🎓 Портфолио\n\n" + "\n\n".join(lines),
        reply_markup=back_keyboard("cabinet:portfolio"),
    )
