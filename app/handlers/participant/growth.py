from datetime import datetime

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import (
    Auction,
    AuctionBid,
    PortfolioItem,
    RewardItem,
    RewardRedemption,
    User,
)
from app.keyboards.common import back_keyboard
from app.keyboards.participant import rewards_keyboard
from app.services.notification_service import notify_admins
from app.services.points_service import total_points
from app.states.growth import (
    AuctionBidStates,
    PortfolioUploadStates,
)
from app.utils.constants import ApplicationStatus
from app.utils.validators import clean_text

router = Router(name="participant_growth")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


@router.callback_query(F.data == "rewards:menu")
async def rewards_menu(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    await call.answer()
    if not _approved(user):
        return
    now = datetime.now().astimezone()
    rewards = (
        await session.scalars(
            select(RewardItem)
            .where(RewardItem.is_active.is_(True))
            .order_by(RewardItem.point_cost)
        )
    ).all()
    auctions = (
        await session.scalars(
            select(Auction).where(
                Auction.status == "active",
                Auction.starts_at <= now,
                Auction.ends_at > now,
            )
        )
    ).all()
    auctions = [
        auction
        for auction in auctions
        if not (auction.audience_filter_json or {}).get("role")
        or (auction.audience_filter_json or {}).get("role") == user.role
    ]
    balance = await total_points(session, user.id)
    body = (
        f"🎁 Возможности за баллы\n\nВаш баланс: {balance} баллов\n\n"
        "Баллы можно обменять на возможности из каталога или использовать в аукционах. "
        "При обмене и после победы в аукционе баллы списываются"
    )
    if not rewards and not auctions:
        body += "\n\nНовых возможностей пока нет — мы сообщим, когда появятся"
    await call.message.answer(body, reply_markup=rewards_keyboard(rewards, auctions))


@router.callback_query(F.data.startswith("reward:view:"))
async def reward_view(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    await call.answer()
    if not _approved(user):
        return
    reward = await session.get(RewardItem, int(call.data.rsplit(":", 1)[-1]))
    if reward is None or not reward.is_active:
        await call.message.answer("Эта возможность уже недоступна")
        return
    balance = await total_points(session, user.id)
    availability = (
        "без ограничения" if reward.quantity is None else str(reward.quantity)
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Обменять {reward.point_cost} баллов",
                    callback_data=f"reward:redeem:{reward.id}",
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="rewards:menu")],
        ]
    )
    await call.message.answer(
        f"🎁 {reward.name}\n\n{reward.description}\n\n"
        f"Стоимость: {reward.point_cost} баллов\n"
        f"Доступно: {availability}\nВаш баланс: {balance}",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("reward:redeem:"))
async def reward_redeem(
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
            RewardRedemption.status.in_(["pending", "answered", "exchanged"]),
        )
    )
    if duplicate:
        await call.message.answer(
            "Ваша заявка на эту возможность уже сохранена — команда ЭРА ответит Вам"
        )
        return
    balance = await total_points(session, user.id)
    if balance < reward.point_cost:
        await call.message.answer(
            f"Сейчас не хватает {reward.point_cost - balance} баллов. "
            "Участвуйте в мероприятиях и заданиях — баланс будет расти"
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

    admin_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 Ответить пользователю",
                    callback_data=f"admin:redemption:answer:{redemption.id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отклонить без списания",
                    callback_data=f"admin:redemption:reject:{redemption.id}",
                )
            ],
        ]
    )
    await call.message.answer(
        "Заявка отправлена команде ЭРА 🙌\n\n"
        "Баллы пока не списаны. Администратор сначала ответит Вам, "
        "а обмен состоится только после окончательного подтверждения"
    )
    username = f"@{user.username}" if user.username else "не указан"
    await notify_admins(
        bot,
        settings,
        f"🎁 Новая заявка на возможность\n\n"
        f"Участник: {user.first_name} {user.last_name or ''}\n"
        f"Telegram: {username}\n"
        f"Возможность: {reward.name}\n"
        f"Стоимость: {reward.point_cost} баллов\n"
        f"Баланс: {balance} баллов\n\n"
        "Баллы ещё не списаны",
        reply_markup=admin_keyboard,
    )


@router.callback_query(F.data.startswith("auction:view:"))
async def auction_view(
    call: CallbackQuery, user: User | None, session: AsyncSession
) -> None:
    await call.answer()
    if not _approved(user):
        return
    auction = await session.get(Auction, int(call.data.rsplit(":", 1)[-1]))
    if auction is None or auction.status != "active":
        await call.message.answer("Этот аукцион уже завершён")
        return
    required_role = (auction.audience_filter_json or {}).get("role")
    if required_role and required_role != user.role:
        await call.message.answer("Этот аукцион открыт для другой группы участников")
        return
    highest = int(
        await session.scalar(
            select(func.coalesce(func.max(AuctionBid.amount), 0)).where(
                AuctionBid.auction_id == auction.id,
                AuctionBid.status == "active",
            )
        )
        or 0
    )
    minimum = max(auction.minimum_bid, highest + auction.bid_step)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Сделать ставку", callback_data=f"auction:bid:{auction.id}"
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="rewards:menu")],
        ]
    )
    await call.message.answer(
        f"🔨 {auction.title}\n\n{auction.description}\n\n"
        f"Текущая ставка: {highest or 'ещё нет'}\n"
        f"Следующая ставка: от {minimum} баллов\n"
        f"Завершение: {auction.ends_at:%d.%m.%Y %H:%M}\n\n"
        "Баллы спишутся только у победителя после решения администратора",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("auction:bid:"))
async def auction_bid_start(
    call: CallbackQuery,
    user: User | None,
    state: FSMContext,
) -> None:
    await call.answer()
    if not _approved(user):
        return
    await state.set_state(AuctionBidStates.amount)
    await state.update_data(auction_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer(
        "Напишите сумму ставки целым числом",
        reply_markup=back_keyboard("rewards:menu"),
    )


@router.message(AuctionBidStates.amount)
async def auction_bid_save(
    message: Message, user: User, session: AsyncSession, state: FSMContext
) -> None:
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        await message.answer("Напишите сумму цифрами, например: 120")
        return
    data = await state.get_data()
    auction = await session.get(Auction, int(data["auction_id"]))
    now = datetime.now().astimezone()
    if auction is None or auction.status != "active" or auction.ends_at <= now:
        await state.clear()
        await message.answer("Аукцион уже завершён")
        return
    required_role = (auction.audience_filter_json or {}).get("role")
    if required_role and required_role != user.role:
        await state.clear()
        await message.answer("Этот аукцион открыт для другой группы участников")
        return
    highest = int(
        await session.scalar(
            select(func.coalesce(func.max(AuctionBid.amount), 0)).where(
                AuctionBid.auction_id == auction.id,
                AuctionBid.status == "active",
            )
        )
        or 0
    )
    minimum = max(auction.minimum_bid, highest + auction.bid_step)
    balance = await total_points(session, user.id)
    if amount < minimum:
        await message.answer(f"Минимальная новая ставка — {minimum} баллов")
        return
    if amount > balance:
        await message.answer(
            f"На Вашем балансе {balance} баллов — ставка не может быть выше"
        )
        return
    bid = await session.scalar(
        select(AuctionBid).where(
            AuctionBid.auction_id == auction.id, AuctionBid.user_id == user.id
        )
    )
    if bid:
        bid.amount = amount
        bid.status = "active"
    else:
        session.add(AuctionBid(auction_id=auction.id, user_id=user.id, amount=amount))
    await state.clear()
    await message.answer(
        f"Ставка {amount} баллов принята. Если кто-то предложит больше, Вы сможете обновить её"
    )


@router.callback_query(F.data == "portfolio:upload")
async def portfolio_upload_start(
    call: CallbackQuery, user: User | None, state: FSMContext
) -> None:
    await call.answer()
    if not _approved(user):
        return
    await state.set_state(PortfolioUploadStates.title)
    await call.message.answer(
        "Как называется достижение или сертификат?",
        reply_markup=back_keyboard("cabinet:portfolio"),
    )


@router.message(PortfolioUploadStates.title)
async def portfolio_upload_title(message: Message, state: FSMContext) -> None:
    title = clean_text(message.text or "", 255)
    if not title:
        await message.answer("Напишите короткое название")
        return
    await state.update_data(portfolio_title=title)
    await state.set_state(PortfolioUploadStates.description)
    await message.answer("Коротко расскажите, где и за что Вы получили это достижение")


@router.message(PortfolioUploadStates.description)
async def portfolio_upload_description(message: Message, state: FSMContext) -> None:
    description = clean_text(message.text or "", 1500)
    if not description:
        await message.answer("Добавьте короткое описание")
        return
    await state.update_data(portfolio_description=description)
    await state.set_state(PortfolioUploadStates.file)
    await message.answer(
        "Прикрепите сертификат или подтверждение файлом либо фотографией"
    )


@router.message(PortfolioUploadStates.file, F.document | F.photo)
async def portfolio_upload_file(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    data = await state.get_data()
    file_id = (
        message.document.file_id if message.document else message.photo[-1].file_id
    )
    item = PortfolioItem(
        user_id=user.id,
        title=data["portfolio_title"],
        item_type="participant_document",
        description=data["portfolio_description"],
        file_id=file_id,
        status="pending",
        submitted_by=user.id,
    )
    session.add(item)
    await session.flush()
    await state.clear()
    await message.answer(
        "Достижение сохранено и отправлено на проверку. После подтверждения оно появится в резюме ЭРА"
    )
    await notify_admins(
        bot,
        settings,
        f"📎 Новое достижение на проверку #{item.id}\n\n"
        f"Участник: {user.first_name} {user.last_name or ''}\n"
        f"Название: {item.title}",
    )


@router.message(PortfolioUploadStates.file)
async def portfolio_upload_wrong_file(message: Message) -> None:
    await message.answer("Прикрепите документ или фотографию")
