from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Auction, AuctionBid, User
from app.handlers.admin.partners_admin import admin_ok
from app.services.notification_service import safe_send
from app.services.points_service import add_points, total_points
from app.states.auction import AuctionAdminStates

router = Router(name="admin_auction_block17")


def auctions_keyboard(auctions: list[Auction]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="➕ Создать лот", callback_data="admin:auction:add")]]
    for auction in auctions:
        icon = "🟢" if auction.status == "active" else "⚪️"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {auction.title[:38]}",
                callback_data=f"admin:auction:view:{auction.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="← Развитие", callback_data="admin:menu:growth")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:auctions")
async def admin_auctions(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    auctions = list((await session.scalars(select(Auction).order_by(Auction.created_at.desc()))).all())
    await call.message.answer(
        "🔨 Аукционы\n\nСоздавайте лоты и подтверждайте победителей после завершения ставок.",
        reply_markup=auctions_keyboard(auctions),
    )


@router.callback_query(F.data == "admin:auction:add")
async def auction_add_start(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    await state.set_state(AuctionAdminStates.title)
    await call.message.answer("Название лота:")


@router.message(AuctionAdminStates.title)
async def auction_title(message: Message, state: FSMContext) -> None:
    title = " ".join((message.text or "").split()).strip()
    if not title:
        await message.answer("Название не должно быть пустым.")
        return
    await state.update_data(title=title[:255])
    await state.set_state(AuctionAdminStates.description)
    await message.answer("Описание лота:")


@router.message(AuctionAdminStates.description)
async def auction_description(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip()
    if not description:
        await message.answer("Описание не должно быть пустым.")
        return
    await state.update_data(description=description[:3000])
    await state.set_state(AuctionAdminStates.minimum_bid)
    await message.answer("Стартовая ставка в баллах:")


@router.message(AuctionAdminStates.minimum_bid)
async def auction_minimum(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Введите положительное целое число.")
        return
    await state.update_data(minimum_bid=int(raw))
    await state.set_state(AuctionAdminStates.bid_step)
    await message.answer("Шаг ставки в баллах:")


@router.message(AuctionAdminStates.bid_step)
async def auction_step(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Введите положительное целое число.")
        return
    await state.update_data(bid_step=int(raw))
    await state.set_state(AuctionAdminStates.ends_at)
    await message.answer("Дата и время завершения в формате ДД.ММ.ГГГГ ЧЧ:ММ")


@router.message(AuctionAdminStates.ends_at)
async def auction_finish_create(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not admin_ok(user, settings, message.from_user.id):
        return
    try:
        ends_at = datetime.strptime((message.text or "").strip(), "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        await message.answer("Неверный формат. Пример: 31.07.2026 20:00")
        return
    now = datetime.now(timezone.utc)
    if ends_at <= now:
        await message.answer("Дата завершения должна быть в будущем.")
        return
    data = await state.get_data()
    auction = Auction(
        title=data["title"],
        description=data["description"],
        audience_filter_json={},
        starts_at=now,
        ends_at=ends_at,
        minimum_bid=int(data["minimum_bid"]),
        bid_step=int(data["bid_step"]),
        winner_count=1,
        status="active",
        created_by=user.id if user else None,
    )
    session.add(auction)
    await session.flush()
    await state.clear()
    await message.answer(
        f"Лот опубликован.\n\n{auction.title}\nСтартовая ставка: {auction.minimum_bid}\nШаг: {auction.bid_step}\nДо: {auction.ends_at:%d.%m.%Y %H:%M}"
    )


@router.callback_query(F.data.startswith("admin:auction:view:"))
async def auction_admin_view(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    auction = await session.get(Auction, int(call.data.rsplit(":", 1)[-1]))
    if not auction:
        await call.message.answer("Лот не найден.")
        return
    bids = list(
        (
            await session.scalars(
                select(AuctionBid)
                .where(AuctionBid.auction_id == auction.id, AuctionBid.status == "active")
                .order_by(AuctionBid.amount.desc(), AuctionBid.created_at)
            )
        ).all()
    )
    top = bids[0].amount if bids else 0
    rows = []
    if auction.status == "active":
        rows.append([
            InlineKeyboardButton(
                text="🏆 Подтвердить победителя",
                callback_data=f"admin:auction:winner:{auction.id}",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="⛔ Закрыть без победителя",
                callback_data=f"admin:auction:cancel:{auction.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="← К аукционам", callback_data="admin:auctions")])
    await call.message.answer(
        f"🔨 {auction.title}\n\n{auction.description}\n\n"
        f"Статус: {auction.status}\n"
        f"Ставок: {len(bids)}\n"
        f"Лучшая ставка: {top or 'нет'}\n"
        f"Завершение: {auction.ends_at:%d.%m.%Y %H:%M}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("admin:auction:winner:"))
async def confirm_winner(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    auction_id = int(call.data.rsplit(":", 1)[-1])
    auction = await session.scalar(select(Auction).where(Auction.id == auction_id).with_for_update())
    if not auction or auction.status != "active":
        await call.message.answer("Этот аукцион уже завершён.")
        return
    bids = list(
        (
            await session.scalars(
                select(AuctionBid)
                .where(AuctionBid.auction_id == auction.id, AuctionBid.status == "active")
                .order_by(AuctionBid.amount.desc(), AuctionBid.created_at)
                .with_for_update()
            )
        ).all()
    )
    if not bids:
        await call.message.answer("Нет активных ставок.")
        return
    winner_bid = None
    winner = None
    for bid in bids:
        candidate = await session.get(User, bid.user_id)
        if not candidate or candidate.is_blocked or candidate.is_archived:
            bid.status = "invalid"
            continue
        balance = await total_points(session, candidate.id)
        if balance < bid.amount:
            bid.status = "invalid"
            continue
        winner_bid = bid
        winner = candidate
        break
    if not winner_bid or not winner:
        await session.flush()
        await call.message.answer("Не найден участник с достаточным балансом. Неподходящие ставки отмечены недействительными.")
        return
    await add_points(
        session,
        user_id=winner.id,
        points=-winner_bid.amount,
        reason=f"Победа в аукционе: {auction.title}",
        approved_by=user.id if user else None,
    )
    winner_bid.status = "winner"
    winner_bid.selected_by = user.id if user else None
    winner_bid.selected_at = datetime.now(timezone.utc)
    for bid in bids:
        if bid.id != winner_bid.id and bid.status == "active":
            bid.status = "lost"
    auction.status = "completed"
    await session.flush()
    await safe_send(
        bot,
        winner.telegram_id,
        f"Вы выиграли аукцион «{auction.title}».\nСписано: {winner_bid.amount} баллов.\nКоманда ЭРА свяжется с Вами для передачи лота.",
    )
    await call.message.answer(
        f"Победитель подтверждён: {winner.first_name} {winner.last_name or ''}\nСтавка: {winner_bid.amount} баллов."
    )


@router.callback_query(F.data.startswith("admin:auction:cancel:"))
async def cancel_auction(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    auction = await session.get(Auction, int(call.data.rsplit(":", 1)[-1]))
    if not auction or auction.status != "active":
        await call.message.answer("Этот аукцион уже завершён.")
        return
    auction.status = "cancelled"
    bids = list((await session.scalars(select(AuctionBid).where(AuctionBid.auction_id == auction.id, AuctionBid.status == "active"))).all())
    for bid in bids:
        bid.status = "cancelled"
    await session.flush()
    await call.message.answer("Аукцион закрыт без победителя. Баллы участников не списывались.")
