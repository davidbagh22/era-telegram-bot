from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Badge, User, UserBadge
from app.services.notification_service import safe_send
from app.services.points_service import add_points, add_portfolio_item, total_points
from app.utils import texts
from app.utils.constants import APPLICATION_STATUS_LABELS, ROLE_LABELS, STATUS_LABELS, Role
from app.utils.validators import clean_text

router = Router(name="admin_user_profile_block3_safe")


class DirectRewardStates(StatesGroup):
    points_amount = State()
    points_reason = State()
    badge_reason = State()


def is_admin(user: User | None, settings: Settings, telegram_id: int, event: CallbackQuery | Message) -> bool:
    if telegram_id in settings.admin_ids or (user and user.role == Role.ADMIN and not user.is_blocked):
        return True
    if not user or user.is_blocked or user.is_archived:
        return False
    active = {g.permission for g in (user.permission_grants or []) if g.is_active}
    if isinstance(event, CallbackQuery):
        data = event.data or ""
        if ":points:" in data or ":badge" in data:
            return "points.award" in active
        if is_profile_callback(data):
            return "people.manage" in active or "people.view" in active
    return bool(active)


async def guard(event: CallbackQuery | Message, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    if not is_admin(user, settings, telegram_id, event):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def profile_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Дать баллы", callback_data=f"admin:user:points:{user_id}"), InlineKeyboardButton(text="🏅 Дать знак", callback_data=f"admin:user:badge:{user_id}")],
        [InlineKeyboardButton(text="Изменить роль", callback_data=f"admin:user:role:{user_id}"), InlineKeyboardButton(text="Изменить статус", callback_data=f"admin:user:status:{user_id}")],
        [InlineKeyboardButton(text="Портфолио", callback_data=f"admin:user:portfolio:{user_id}")],
        [InlineKeyboardButton(text="🗄 Удалить доступ", callback_data=f"admin:user:archive:{user_id}")],
        [InlineKeyboardButton(text="← К списку", callback_data="admin:participants")],
    ])


def is_profile_callback(data: str | None) -> bool:
    parts = (data or "").split(":")
    return len(parts) == 3 and parts[0] == "admin" and parts[1] == "user" and parts[2].isdigit()


async def profile_text(session: AsyncSession, target: User) -> str:
    balance = await total_points(session, target.id)
    departments = ", ".join(link.department.name for link in target.departments) or "не выбраны"
    directions = ", ".join(link.direction.name for link in target.directions) or "не выбраны"
    badges = (await session.scalars(select(Badge).join(UserBadge, UserBadge.badge_id == Badge.id).where(UserBadge.user_id == target.id).order_by(Badge.name))).all()
    badge_names = ", ".join(badge.name for badge in badges) or "пока нет"
    telegram = f"@{target.username}" if target.username else str(target.telegram_id)
    return (
        f"👤 Участник #{target.id}\n\n{target.first_name} {target.last_name or ''}\n"
        f"Роль: {ROLE_LABELS.get(target.role, target.role)}\n"
        f"Статус: {STATUS_LABELS.get(target.participation_status, target.participation_status)}\n"
        f"Заявка: {APPLICATION_STATUS_LABELS.get(target.application_status, target.application_status)}\n\n"
        f"🎂 Возраст: {target.age or 'не указан'}\n📍 Город: {target.city or 'не указан'}\n"
        f"📱 Телефон: {target.phone or 'не указан'}\n📧 Email: {target.email or 'не указан'}\n💬 Telegram: {telegram}\n\n"
        f"🏛 Департаменты: {departments}\n📌 Направления: {directions}\n\n⭐ Баланс: {balance} баллов\n🏅 Знаки: {badge_names}"
    )


@router.callback_query(F.data.startswith("admin:user:points:"))
async def points_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession) -> None:
    if not await guard(call, user, settings):
        return
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if not target:
        await call.message.answer("Участник не найден")
        return
    await state.set_state(DirectRewardStates.points_amount)
    await state.update_data(profile_target_id=target.id)
    await call.message.answer(f"Баллы для: {target.first_name} {target.last_name or ''}\n\nСколько баллов изменить? Положительное число начислит, отрицательное спишет.")


@router.message(DirectRewardStates.points_amount)
async def points_amount(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await guard(message, user, settings):
        return
    try:
        amount = int((message.text or "").strip())
        if amount == 0 or abs(amount) > 10000:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число от -10000 до 10000, кроме нуля")
        return
    await state.update_data(profile_points_amount=amount)
    await state.set_state(DirectRewardStates.points_reason)
    await message.answer("За что меняем баллы? Напишите короткую причину.")


@router.message(DirectRewardStates.points_reason)
async def points_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await guard(message, user, settings):
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
    await message.answer(f"Готово. Баланс участника: {balance} баллов", reply_markup=profile_kb(target.id))
    await safe_send(bot, target.telegram_id, f"Ваш баланс изменён на {amount:+d} баллов\nПричина: {reason}\n\nТекущий баланс: {balance} баллов")


@router.callback_query(F.data.startswith("admin:user:badge:"))
async def badge_start(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await guard(call, user, settings):
        return
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if not target:
        await call.message.answer("Участник не найден")
        return
    owned = set((await session.scalars(select(UserBadge.badge_id).where(UserBadge.user_id == target.id))).all())
    badges = [b for b in (await session.scalars(select(Badge).order_by(Badge.name))).all() if b.id not in owned]
    if not badges:
        await call.message.answer("У участника уже есть все доступные знаки.", reply_markup=profile_kb(target.id))
        return
    rows = [[InlineKeyboardButton(text=b.name, callback_data=f"admin:user:badge_select:{target.id}:{b.id}")] for b in badges]
    rows.append([InlineKeyboardButton(text="← К участнику", callback_data=f"admin:user:{target.id}")])
    await state.clear()
    await call.message.answer("Выберите знак. Показываются только те, которых у участника ещё нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("admin:user:badge_select:"))
async def badge_select(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await guard(call, user, settings):
        return
    parts = call.data.split(":")
    target = await session.get(User, int(parts[3]))
    badge = await session.get(Badge, int(parts[4]))
    if not target or not badge:
        await call.message.answer("Участник или знак не найден")
        return
    exists = await session.scalar(select(UserBadge).where(UserBadge.user_id == target.id, UserBadge.badge_id == badge.id))
    if exists:
        await call.message.answer("У участника уже есть этот знак. Повторно не выдаю.", reply_markup=profile_kb(target.id))
        return
    await state.set_state(DirectRewardStates.badge_reason)
    await state.update_data(profile_target_id=target.id, profile_badge_id=badge.id)
    await call.message.answer(f"За что участник получает знак «{badge.name}»?")


@router.message(DirectRewardStates.badge_reason)
async def badge_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await guard(message, user, settings):
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
        await message.answer("Участник уже получил этот знак ранее.", reply_markup=profile_kb(target.id))
        return
    session.add(UserBadge(user_id=target.id, badge_id=badge.id, reason=reason, awarded_by=user.id if user else None))
    await add_portfolio_item(session, user_id=target.id, title=badge.name, item_type="badge", description=reason, issued_by=user.id if user else None)
    await state.clear()
    await message.answer("Знак выдан и добавлен в портфолио.", reply_markup=profile_kb(target.id))
    await safe_send(bot, target.telegram_id, f"Вы получили знак «{badge.name}» 🌟\n\n{reason}")


@router.callback_query(F.data.func(is_profile_callback))
async def profile(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await guard(call, user, settings):
        return
    await state.clear()
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if not target:
        await call.message.answer("Участник не найден")
        return
    await call.message.answer(await profile_text(session, target), reply_markup=profile_kb(target.id))
