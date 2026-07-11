from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Auction, AuctionBid, User
from app.services.points_service import total_points
from app.states.auction import AuctionBidStates
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="participant_auction_block17")


def approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


def auction_list_keyboard(auctions: list[Auction]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"🔨 {auction.title[:42]}", callback_data=f"auction:view:{auction.id}")]
        for auction in auctions
    ]
    rows.append([InlineKeyboardButton(text="← Возможности", callback_data="offers:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _top_bid(session: AsyncSession, auction_id: int) -> int:
    return int(
        await session.scalar(
            select(func.coalesce(func.max(AuctionBid.amount), 0)).where(
                AuctionBid.auction_id == auction_id,
                AuctionBid.status == "active",
            )
        )
        or 0
    )


@router.callback_query(F.data == "auctions:list")
async def auctions_list(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    now = datetime.now(timezone.utc)
    auctions = list(
        (
            await session.scalars(
                select(Auction)
                .where(
                    Auction.status == "active",
                    Auction.starts_at <= now,
                    Auction.ends_at > now,
                )
                .order_by(Auction.ends_at)
            )
        ).all()
    )
    if not auctions:
        await call.message.answer(
            "🔨 Аукцион\n\nАктивных лотов пока нет. Когда появится новый аукцион, он будет доступен здесь.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="← Возможности", callback_data="offers:menu")]]
            ),
        )
        return
    await call.message.answer(
        "🔨 Аукцион ЭРА\n\nСтавки делаются баллами. Баллы списываются только после подтверждения победителя администратором.",
        reply_markup=auction_list_keyboard(auctions),
    )


@router.callback_query(F.data.startswith("auction:view:"))
async def auction_view(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    auction = await session.get(Auction, int(call.data.rsplit(":", 1)[-1]))
    if not auction:
        await call.message.answer("Лот не найден.")
        return
    now = datetime.now(timezone.utc)
    top = await _top_bid(session, auction.id)
    current = await session.scalar(
        select(AuctionBid).where(
            AuctionBid.auction_id == auction.id,
            AuctionBid.user_id == user.id,
        )
    )
    next_bid = max(auction.minimum_bid, top + auction.bid_step if top else auction.minimum_bid)
    active = auction.status == "active" and auction.starts_at <= now < auction.ends_at
    text = (
        f"🔨 {auction.title}\n\n{auction.description}\n\n"
        f"Текущая ставка: {top or 'ставок пока нет'}\n"
        f"Минимальная следующая ставка: {next_bid} баллов\n"
        f"Шаг: {auction.bid_step} баллов\n"
        f"Завершение: {auction.ends_at:%d.%m.%Y %H:%M}"
    )
    if current:
        text += f"\nВаша ставка: {current.amount} баллов"
    rows = []
    if active:
        rows.append([InlineKeyboardButton(text="Сделать ставку", callback_data=f"auction:bid:{auction.id}")])
    else:
        text += "\n\nПриём ставок завершён."
    rows.append([InlineKeyboardButton(text="← К аукционам", callback_data="auctions:list")])
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("auction:bid:"))
async def auction_bid_start(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    auction = await session.get(Auction, int(call.data.rsplit(":", 1)[-1]))
    now = datetime.now(timezone.utc)
    if not auction or auction.status != "active" or not (auction.starts_at <= now < auction.ends_at):
        await call.message.answer("Приём ставок на этот лот уже закрыт.")
        return
    top = await _top_bid(session, auction.id)
    minimum = max(auction.minimum_bid, top + auction.bid_step if top else auction.minimum_bid)
    balance = await total_points(session, user.id)
    await state.set_state(AuctionBidStates.amount)
    await state.update_data(auction_id=auction.id)
    await call.message.answer(
        f"Введите ставку целым числом.\n\nМинимум: {minimum} баллов\nВаш баланс: {balance} баллов"
    )


@router.message(AuctionBidStates.amount)
async def auction_bid_save(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Введите положительное целое число.")
        return
    amount = int(raw)
    data = await state.get_data()
    auction_id = int(data["auction_id"])
    auction = await session.scalar(
        select(Auction).where(Auction.id == auction_id).with_for_update()
    )
    now = datetime.now(timezone.utc)
    if not auction or auction.status != "active" or not (auction.starts_at <= now < auction.ends_at):
        await state.clear()
        await message.answer("Приём ставок на этот лот уже закрыт.")
        return
    top = await _top_bid(session, auction.id)
    minimum = max(auction.minimum_bid, top + auction.bid_step if top else auction.minimum_bid)
    existing = await session.scalar(
        select(AuctionBid).where(
            AuctionBid.auction_id == auction.id,
            AuctionBid.user_id == user.id,
        )
    )
    if existing and existing.status == "active" and existing.amount == top:
        minimum = max(minimum, existing.amount + auction.bid_step)
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
    await message.answer(
        f"Ставка принята: {amount} баллов.\n\nБаллы пока не списаны. Они спишутся только при подтверждении победы администратором."
    )
