from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Auction, AuctionBid, User
from app.services.auction_service import bidder_name, format_local, is_open, remaining_time, top_bid_with_user
from app.services.points_service import total_points
from app.states.auction import AuctionBidStates
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="participant_auction_block17")


def approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


def auction_list_keyboard(auctions: list[Auction]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"🔨 {auction.title[:42]}", callback_data=f"auction:view:{auction.id}")] for auction in auctions]
    rows.append([InlineKeyboardButton(text="← Возможности", callback_data="offers:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "auctions:list")
async def auctions_list(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    now = datetime.now(timezone.utc)
    auctions = list((await session.scalars(select(Auction).where(Auction.status == "active", Auction.starts_at <= now, Auction.ends_at > now).order_by(Auction.ends_at))).all())
    if not auctions:
        await call.message.answer("🔨 Аукцион\n\nАктивных лотов пока нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← Возможности", callback_data="offers:menu")]]))
        return
    await call.message.answer("🔨 Аукцион ЭРА\n\nСтавки делаются баллами. Баллы списываются только после подтверждения победителя администратором.", reply_markup=auction_list_keyboard(auctions))


@router.callback_query(F.data.startswith("auction:view:"))
async def auction_view(call: CallbackQuery, user: User | None, session: AsyncSession, settings: Settings) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    auction = await session.get(Auction, int(call.data.rsplit(":", 1)[-1]))
    if not auction:
        await call.message.answer("Лот не найден.")
        return
    top_bid, top_user = await top_bid_with_user(session, auction.id)
    top = top_bid.amount if top_bid else 0
    current = await session.scalar(select(AuctionBid).where(AuctionBid.auction_id == auction.id, AuctionBid.user_id == user.id))
    next_bid = max(auction.minimum_bid, top + auction.bid_step if top else auction.minimum_bid)
    active = is_open(auction)
    text = (
        f"🔨 {auction.title}\n\n{auction.description}\n\n"
        f"Последняя ставка: {top if top else 'ставок пока нет'}\n"
        f"Лидер: {bidder_name(top_user) if top_bid else 'пока нет'}\n"
        f"Минимальная следующая ставка: {next_bid} баллов\n"
        f"Шаг: {auction.bid_step} баллов\n"
        f"Завершение: {format_local(auction.ends_at, settings.timezone)}\n"
        f"Осталось: {remaining_time(auction.ends_at)}"
    )
    if current:
        text += f"\nВаша ставка: {current.amount} баллов"
    rows = []
    if active:
        rows.append([InlineKeyboardButton(text="Сделать ставку", callback_data=f"auction:bid:{auction.id}")])
    else:
        text += "\n\nПриём ставок завершён. Победителя подтвердит администратор."
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"auction:view:{auction.id}")])
    rows.append([InlineKeyboardButton(text="← К аукционам", callback_data="auctions:list")])
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("auction:bid:"))
async def auction_bid_start(call: CallbackQuery, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    auction = await session.get(Auction, int(call.data.rsplit(":", 1)[-1]))
    if not auction or not is_open(auction):
        await call.message.answer("Приём ставок на этот лот уже закрыт.")
        return
    top_bid, _ = await top_bid_with_user(session, auction.id)
    top = top_bid.amount if top_bid else 0
    minimum = max(auction.minimum_bid, top + auction.bid_step if top else auction.minimum_bid)
    balance = await total_points(session, user.id)
    await state.set_state(AuctionBidStates.amount)
    await state.update_data(auction_id=auction.id)
    await call.message.answer(f"Введите ставку целым числом.\n\nМинимум: {minimum} баллов\nВаш баланс: {balance} баллов")


@router.message(AuctionBidStates.amount)
async def auction_bid_save(message: Message, user: User, session: AsyncSession, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Введите положительное целое число.")
        return
    amount = int(raw)
    auction_id = int((await state.get_data())["auction_id"])
    auction = await session.scalar(select(Auction).where(Auction.id == auction_id).with_for_update())
    if not auction or not is_open(auction):
        await state.clear()
        await message.answer("Приём ставок на этот лот уже закрыт.")
        return
    top_bid, _ = await top_bid_with_user(session, auction.id)
    top = top_bid.amount if top_bid else 0
    minimum = max(auction.minimum_bid, top + auction.bid_step if top else auction.minimum_bid)
    existing = await session.scalar(select(AuctionBid).where(AuctionBid.auction_id == auction.id, AuctionBid.user_id == user.id))
    if amount < minimum:
        await message.answer(f"Ставка слишком мала. Минимальная ставка сейчас: {minimum} баллов.")
        return
    balance = await total_points(session, user.id)
    if balance < amount:
        await message.answer(f"Недостаточно баллов. Ваш баланс: {balance}.")
        return
    if existing:
        existing.amount = amount
        existing.status = "active"
        existing.selected_by = None
        existing.selected_at = None
    else:
        session.add(AuctionBid(auction_id=auction.id, user_id=user.id, amount=amount, status="active"))
    await session.flush()
    await state.clear()
    await message.answer(f"Ставка принята: {amount} баллов.\n\nБаллы пока не списаны. Теперь ставка отображается в карточке лота. Списание произойдёт только после подтверждения победителя администратором.")
