from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Badge, PointTransaction, User, UserBadge
from app.services.notification_service import safe_send
from app.services.points_service import add_points, add_portfolio_item, total_points
from app.utils import texts
from app.utils.constants import APPLICATION_STATUS_LABELS, ROLE_LABELS, STATUS_LABELS, Role
from app.utils.validators import clean_text

router = Router(name="admin_user_profile_block3")


class UserProfileRewardStates(StatesGroup):
    points_amount = State()
    points_reason = State()
    badge_reason = State()


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (user and not user.is_blocked and any(grant.is_active for grant in (user.permission_grants or [])))
    )


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


def _telegram(target: User) -> str:
    return f"@{target.username}" if target.username else str(target.telegram_id)


def _profile_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Дать баллы", callback_data=f"admin:user:points:{user_id}"),
                InlineKeyboardButton(text="🏅 Дать знак", callback_data=f"admin:user:badge:{user_id}"),
            ],
            [
                InlineKeyboardButton(text="Изменить роль", callback_data=f"admin:user:role:{user_id}"),
                InlineKeyboardButton(text="Изменить статус", callback_data=f"admin:user:status:{user_id}"),
            ],
            [InlineKeyboardButton(text="Портфолио", callback_data=f"admin:user:portfolio:{user_id}")],
            [InlineKeyboardButton(text="← К списку", callback_data="admin:participants")],
        ]
    )


async def _profile_text(session: AsyncSession, target: User) -> str:
    balance = await total_points(session, target.id)
    departments = ", ".join(link.department.name for link in target.departments) or "не выбраны"
    directions = ", ".join(link.direction.name for link in target.directions) or "не выбраны"
    badges = (
        await session.scalars(
            select(Badge)
            .join(UserBadge, UserBadge.badge_id == Badge.id)
            .where(UserBadge.user_id == target.id)
            .order_by(Badge.name)
        )
    ).all()
    badge_names = ", ".join(badge.name for badge in badges) or "пока нет"
    return (
        f"👤 Участник #{target.id}\n\n"
        f"{target.first_name} {target.last_name or ''}\n"
        f"Роль: {ROLE_LABELS.get(target.role, target.role)}\n"
        f"Статус: {STATUS_LABELS.get(target.participation_status, target.participation_status)}\n"
        f"Заявка: {APPLICATION_STATUS_LABELS.get(target.application_status, target.application_status)}\n\n"
        f"🎂 Возраст: {target.age or 'не указан'}\n"
        f"📍 Город: {target.city or 'не указан'}\n"
        f"📱 Телефон: {target.phone or 'не указан'}\n"
        f"📧 Email: {target.email or 'не указан'}\n"
        f"💬 Telegram: {_telegram(target)}\n\n"
        f"🏛 Департаменты: {departments}\n"
        f"📌 Направления: {directions}\n\n"
        f"⭐ Баланс: {balance} баллов\n"
        f"🏅 Знаки: {badge_names}"
    )


@router.callback_query(F.data.startswith("admin:user:"))
async def user_profile_router(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    parts = call.data.split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        return
    if not await _guard(call, user, settings):
        return
    await state.clear()
    target = await session.get(User, int(parts[2]))
    if not target:
        await call.message.answer("Участник не найден")
        return
    await call.message.answer(await _profile_text(session, target), reply_markup=_profile_keyboard(target.id))


@router.callback_query(F.data.startswith("admin:user:points:"))
async def points_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if not target:
        await call.message.answer("Участник не найден")
        return
    await state.set_state(UserProfileRewardStates.points_amount)
    await state.update_data(profile_target_id=target.id)
    await call.message.answer(
        f"Баллы для: {target.first_name} {target.last_name or ''}\n\n"
        "Сколько баллов изменить?\nПоложительное число начислит, отрицательное спишет."
    )


@router.message(UserProfileRewardStates.points_amount)
async def points_amount(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    try:
        amount = int((message.text or "").strip())
        if amount == 0 or abs(amount) > 10000:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число от -10000 до 10000, кроме нуля")
        return
    await state.update_data(profile_points_amount=amount)
    await state.set_state(UserProfileRewardStates.points_reason)
    await message.answer("За что меняем баллы? Напишите короткую причину.")


@router.message(UserProfileRewardStates.points_reason)
async def points_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(message, user, settings):
        return
    reason = clean_text(message.text or "", 500)
    if not reason:
        await message.answer("Причина обязательна")
        return
    data = await state.get_data()
    target = await session.get(User, int(data["profile_target_id"]))
    if not target:
        await state.clear()
        await message.answer("Участник не найден")
        return
    amount = int(data["profile_points_amount"])
    await add_points(session, user_id=target.id, points=amount, reason=reason, approved_by=user.id if user else None)
    await state.clear()
    balance = await total_points(session, target.id)
    await message.answer(f"Готово. Баланс участника: {balance} баллов", reply_markup=_profile_keyboard(target.id))
    await safe_send(bot, target.telegram_id, f"Ваш баланс изменён на {amount:+d} баллов\nПричина: {reason}\n\nТекущий баланс: {balance} баллов")


@router.callback_query(F.data.startswith("admin:user:badge:"))
async def badge_start(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if not target:
        await call.message.answer("Участник не найден")
        return
    owned_ids = set((await session.scalars(select(UserBadge.badge_id).where(UserBadge.user_id == target.id))).all())
    badges = (await session.scalars(select(Badge).order_by(Badge.name))).all()
    available = [badge for badge in badges if badge.id not in owned_ids]
    if not available:
        await call.message.answer("У участника уже есть все доступные знаки.", reply_markup=_profile_keyboard(target.id))
        return
    await state.clear()
    rows = [
        [InlineKeyboardButton(text=badge.name, callback_data=f"admin:user:badge_select:{target.id}:{badge.id}")]
        for badge in available
    ]
    rows.append([InlineKeyboardButton(text="← К участнику", callback_data=f"admin:user:{target.id}")])
    await call.message.answer(
        f"Выберите знак для {target.first_name} {target.last_name or ''}\n\n"
        "Показываются только знаки, которых у участника ещё нет.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("admin:user:badge_select:"))
async def badge_select(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    parts = call.data.split(":")
    if len(parts) != 5 or not parts[3].isdigit() or not parts[4].isdigit():
        return
    target = await session.get(User, int(parts[3]))
    badge = await session.get(Badge, int(parts[4]))
    if not target or not badge:
        await call.message.answer("Участник или знак не найден")
        return
    exists = await session.scalar(select(UserBadge).where(UserBadge.user_id == target.id, UserBadge.badge_id == badge.id))
    if exists:
        await call.message.answer("У участника уже есть этот знак. Повторно не выдаю.", reply_markup=_profile_keyboard(target.id))
        return
    await state.set_state(UserProfileRewardStates.badge_reason)
    await state.update_data(profile_target_id=target.id, profile_badge_id=badge.id)
    await call.message.answer(f"За что участник получает знак «{badge.name}»?")


@router.message(UserProfileRewardStates.badge_reason)
async def badge_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(message, user, settings):
        return
    reason = clean_text(message.text or "", 500)
    if not reason:
        await message.answer("Причина обязательна")
        return
    data = await state.get_data()
    target = await session.get(User, int(data["profile_target_id"]))
    badge = await session.get(Badge, int(data["profile_badge_id"]))
    if not target or not badge:
        await state.clear()
        await message.answer("Участник или знак не найден")
        return
    exists = await session.scalar(select(UserBadge).where(UserBadge.user_id == target.id, UserBadge.badge_id == badge.id))
    if exists:
        await state.clear()
        await message.answer("Участник уже получил этот знак ранее.", reply_markup=_profile_keyboard(target.id))
        return
    session.add(UserBadge(user_id=target.id, badge_id=badge.id, reason=reason, awarded_by=user.id if user else None))
    await add_portfolio_item(session, user_id=target.id, title=badge.name, item_type="badge", description=reason, issued_by=user.id if user else None)
    await state.clear()
    await message.answer("Знак выдан и добавлен в портфолио.", reply_markup=_profile_keyboard(target.id))
    await safe_send(bot, target.telegram_id, f"Вы получили знак «{badge.name}» 🌟\n\n{reason}")
