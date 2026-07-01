from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Badge, User, UserBadge
from app.services.points_service import add_points
from app.utils import texts
from app.utils.constants import Role

router = Router(name="admin_user_reward_direct")


class DirectUserRewardStates(StatesGroup):
    points_amount = State()
    points_reason = State()
    badge_reason = State()


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (user and not user.is_blocked and any(g.is_active for g in (user.permission_grants or [])))
    )


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


@router.callback_query(F.data.startswith("admin:user:points:"))
async def points_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(DirectUserRewardStates.points_amount)
    await state.update_data(target_user_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer("Сколько баллов начислить? Можно указать отрицательное число для списания.")


@router.message(DirectUserRewardStates.points_amount)
async def points_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = int((message.text or "").strip())
        if amount == 0 or abs(amount) > 1000:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от -1000 до 1000, кроме нуля")
        return
    await state.update_data(points_amount=amount)
    await state.set_state(DirectUserRewardStates.points_reason)
    await message.answer("За что начисляем / списываем баллы?")


@router.message(DirectUserRewardStates.points_reason)
async def points_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    reason = (message.text or "").strip()[:500]
    if not reason:
        await message.answer("Причина обязательна")
        return
    await add_points(session, user_id=int(data["target_user_id"]), points=int(data["points_amount"]), reason=reason, approved_by=user.id if user else None)
    await state.clear()
    await message.answer("Баллы изменены")


@router.callback_query(F.data.startswith("admin:user:badge:"))
async def badge_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    target_id = int(call.data.rsplit(":", 1)[-1])
    owned = set((await session.scalars(select(UserBadge.badge_id).where(UserBadge.user_id == target_id))).all())
    badges = (await session.scalars(select(Badge).where(~Badge.id.in_(owned or {-1})).order_by(Badge.id))).all()
    if not badges:
        await call.message.answer("У пользователя уже есть все доступные знаки")
        return
    await state.update_data(target_user_id=target_id)
    rows = [[InlineKeyboardButton(text=f"#{badge.id} · {badge.name}", callback_data=f"admin:user:badge_choose:{badge.id}")] for badge in badges]
    await call.message.answer("Какой знак вручить?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("admin:user:badge_choose:"))
async def badge_choose(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.update_data(badge_id=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(DirectUserRewardStates.badge_reason)
    await call.message.answer("За что вручаем знак?")


@router.message(DirectUserRewardStates.badge_reason)
async def badge_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    reason = (message.text or "").strip()[:500]
    if not reason:
        await message.answer("Причина обязательна")
        return
    session.add(UserBadge(user_id=int(data["target_user_id"]), badge_id=int(data["badge_id"]), reason=reason, awarded_by=user.id if user else None))
    await state.clear()
    await message.answer("Знак выдан")
