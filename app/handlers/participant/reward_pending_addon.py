from aiogram import F, Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import RewardItem, RewardRedemption, User
from app.services.notification_service import notify_admins
from app.services.points_service import total_points
from app.utils.constants import ApplicationStatus

router = Router(name="participant_reward_pending_addon")


def _approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


def _admin_keyboard(redemption_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Ответить пользователю", callback_data=f"admin:redemption:reply:{redemption_id}")],
            [InlineKeyboardButton(text="✅ Обменять и списать баллы", callback_data=f"admin:redemption:exchange:{redemption_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:redemption:reject:{redemption_id}")],
        ]
    )


@router.callback_query(F.data.startswith("reward:redeem:"))
async def reward_redeem_pending(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    await call.answer()
    if not _approved(user):
        return
    reward = await session.get(RewardItem, int(call.data.rsplit(":", 1)[-1]))
    if reward is None or not reward.is_active or reward.quantity == 0:
        await call.message.answer("Эта возможность уже недоступна")
        return
    duplicate = await session.scalar(
        select(RewardRedemption).where(
            RewardRedemption.reward_id == reward.id,
            RewardRedemption.user_id == user.id,
            RewardRedemption.status.in_(["pending", "reserved", "approved"]),
        )
    )
    if duplicate:
        await call.message.answer("Ваша заявка на эту возможность уже у администратора")
        return
    balance = await total_points(session, user.id)
    if balance < reward.point_cost:
        await call.message.answer(
            f"Сейчас не хватает {reward.point_cost - balance} баллов. Участвуйте в мероприятиях и заданиях — баланс будет расти"
        )
        return
    redemption = RewardRedemption(
        reward_id=reward.id,
        user_id=user.id,
        points_spent=reward.point_cost,
        status="pending",
    )
    session.add(redemption)
    await session.flush()
    await call.message.answer(
        "Заявка отправлена админу. Баллы пока не списаны.\n\n"
        "Админ ответит Вам, после этого сможет подтвердить обмен и списать баллы."
    )
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    await notify_admins(
        bot,
        settings,
        f"🎁 Новая заявка на возможность\n\n"
        f"Участник: {user.first_name} {user.last_name or ''}\n"
        f"Telegram: {telegram}\n"
        f"Возможность: {reward.name}\n"
        f"Стоимость: {reward.point_cost} баллов\n"
        f"Баланс участника: {balance} баллов\n\n"
        "Баллы ещё не списаны.",
        reply_markup=_admin_keyboard(redemption.id),
    )
