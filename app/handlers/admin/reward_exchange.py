from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import RewardItem, RewardRedemption, User
from app.services.notification_service import safe_send
from app.services.points_service import add_points, total_points
from app.utils import texts
from app.utils.constants import Role

router = Router(name="admin_reward_exchange")


class RewardExchangeStates(StatesGroup):
    reply = State()
    reject_reason = State()


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


async def _context(session: AsyncSession, item_id: int):
    redemption = await session.get(RewardRedemption, item_id)
    if not redemption:
        return None, None, None
    reward = await session.get(RewardItem, redemption.reward_id)
    target = await session.get(User, redemption.user_id)
    return redemption, reward, target


def _keyboard(redemption: RewardRedemption) -> InlineKeyboardMarkup:
    rows = []
    if redemption.status in {"pending", "reserved"}:
        rows.append([
            InlineKeyboardButton(
                text="💬 Ответить пользователю",
                callback_data=f"admin:redemption:reply:{redemption.id}",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="✅ Обменять и списать баллы",
                callback_data=f"admin:redemption:exchange:{redemption.id}",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="❌ Отклонить без списания",
                callback_data=f"admin:redemption:reject:{redemption.id}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _status_label(status: str) -> str:
    return {
        "pending": "ждёт ответа админа",
        "reserved": "ответ отправлен, ждёт обмена",
        "approved": "обмен завершён",
        "rejected": "отклонена",
    }.get(status, status)


@router.callback_query(F.data == "admin:reward:redemptions")
async def reward_redemptions_unified(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    items = (
        await session.scalars(
            select(RewardRedemption)
            .where(RewardRedemption.status.in_(["pending", "reserved"]))
            .order_by(RewardRedemption.created_at)
        )
    ).all()
    if not items:
        await call.message.answer("Новых заявок на возможности нет")
        return
    await call.message.answer(f"🎁 Заявки на возможности: {len(items)}")
    for item in items:
        reward = await session.get(RewardItem, item.reward_id)
        target = await session.get(User, item.user_id)
        if not reward or not target:
            continue
        balance = await total_points(session, target.id)
        telegram = f"@{target.username}" if target.username else str(target.telegram_id)
        await call.message.answer(
            f"🎁 Заявка #{item.id}\n\n"
            f"Возможность: {reward.name}\n"
            f"Стоимость: {reward.point_cost} баллов\n"
            f"Статус: {_status_label(item.status)}\n\n"
            f"Участник: {target.first_name} {target.last_name or ''}\n"
            f"Telegram: {telegram}\n"
            f"Телефон: {target.phone or 'не указан'}\n"
            f"Баланс сейчас: {balance} баллов\n\n"
            f"Ответ админа:\n{item.admin_comment or 'ещё не отправлен'}\n\n"
            "Баллы будут списаны только после финальной кнопки обмена.",
            reply_markup=_keyboard(item),
        )


@router.callback_query(F.data.startswith("admin:redemption:reply:"))
async def reward_reply_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(RewardExchangeStates.reply)
    await state.update_data(redemption_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer("Напишите ответ пользователю. После ответа можно будет подтвердить выдачу возможности.")


@router.message(RewardExchangeStates.reply)
async def reward_reply_send(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    redemption, reward, target = await _context(session, int(data["redemption_id"]))
    if not redemption or not reward or not target:
        await state.clear()
        await message.answer("Заявка не найдена")
        return
    if redemption.status not in {"pending", "reserved"}:
        await state.clear()
        await message.answer("Эта заявка уже закрыта")
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Сообщение не может быть пустым")
        return
    redemption.admin_comment = text
    redemption.status = "reserved"
    redemption.reviewed_by = user.id if user else None
    await safe_send(bot, target.telegram_id, f"Ответ по возможности «{reward.name}":\n\n{text}\n\nБаллы будут списаны только после финального подтверждения админа.")
    await state.clear()
    await message.answer("Ответ отправлен пользователю. Теперь можно подтвердить обмен и списать баллы.")


@router.callback_query(F.data.startswith("admin:redemption:exchange:"))
@router.callback_query(F.data.startswith("admin:redemption:approve:"))
async def reward_confirm(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(call, user, settings):
        return
    redemption, reward, target = await _context(session, int(call.data.rsplit(":", 1)[-1]))
    if not redemption or not reward or not target:
        await call.message.answer("Заявка не найдена")
        return
    if redemption.status == "approved":
        await call.message.answer("Эта заявка уже подтверждена. Повторно баллы не списываю.")
        return
    if redemption.status == "rejected":
        await call.message.answer("Эта заявка уже отклонена")
        return
    if not redemption.admin_comment or redemption.status != "reserved":
        await call.message.answer("Сначала отправьте ответ пользователю через кнопку «Ответить пользователю». Только после этого можно обменять и списать баллы.")
        return
    if reward.quantity == 0:
        await call.message.answer("Возможность закончилась.")
        return
    balance = await total_points(session, target.id)
    if balance < reward.point_cost:
        await call.message.answer(f"У участника уже не хватает баллов. Баланс: {balance}, нужно: {reward.point_cost}")
        return
    redemption.status = "approved"
    redemption.reviewed_by = user.id if user else None
    redemption.points_spent = reward.point_cost
    if reward.quantity is not None:
        reward.quantity -= 1
    await add_points(session, user_id=target.id, points=-reward.point_cost, reason=f"Получение возможности: {reward.name}", approved_by=user.id if user else None)
    await safe_send(bot, target.telegram_id, f"Возможность «{reward.name}» подтверждена.\n\nСписано: {reward.point_cost} баллов.")
    await call.message.answer("Возможность подтверждена. Баллы списаны, пользователь уведомлён.")


@router.callback_query(F.data.startswith("admin:redemption:reject:"))
async def reward_reject_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(RewardExchangeStates.reject_reason)
    await state.update_data(redemption_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer("Напишите причину отклонения заявки. Баллы списаны не будут.")


@router.message(RewardExchangeStates.reject_reason)
async def reward_reject_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    redemption, reward, target = await _context(session, int(data["redemption_id"]))
    if not redemption or not reward or not target:
        await state.clear()
        await message.answer("Заявка не найдена")
        return
    if redemption.status == "approved":
        await state.clear()
        await message.answer("Заявка уже обменяна, отклонить нельзя")
        return
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("Причина обязательна")
        return
    redemption.status = "rejected"
    redemption.admin_comment = reason
    redemption.reviewed_by = user.id if user else None
    await safe_send(bot, target.telegram_id, f"Заявка на возможность «{reward.name}» отклонена.\n\nПричина: {reason}\n\nБаллы не списаны.")
    await state.clear()
    await message.answer("Заявка отклонена. Баллы не списаны.")
