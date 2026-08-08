from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Auction, AuctionBid, User
from app.services.audit_service import audit
from app.services.points_service import add_points, total_points

# Points-based auctions — app/handlers/participant/auction_block17.py (bid)
# and app/handlers/admin/auction_block17.py (create lot, confirm winner,
# mark delivered, cancel). Points are only ever moved once a winner is
# confirmed by an admin; a bid alone never touches a balance.

BID_ERROR_CLOSED = "auction_closed"
BID_ERROR_BELOW_MINIMUM = "bid_too_low"
BID_ERROR_INSUFFICIENT_POINTS = "insufficient_points"


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def format_local(value: datetime, timezone_name: str) -> str:
    return as_utc(value).astimezone(ZoneInfo(timezone_name)).strftime("%d.%m.%Y %H:%M")


def remaining_time(ends_at: datetime, now: datetime | None = None) -> str:
    seconds = int((as_utc(ends_at) - (now or datetime.now(timezone.utc))).total_seconds())
    if seconds <= 0:
        return "завершён"
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} дн. {hours} ч. {minutes} мин."
    if hours:
        return f"{hours} ч. {minutes} мин."
    return f"{max(minutes, 1)} мин."


def bidder_name(user: User | None) -> str:
    if not user:
        return "участник ЭРА"
    name = f"{user.first_name} {user.last_name or ''}".strip()
    return f"{name} (@{user.username})" if user.username else name


async def top_bid_with_user(session: AsyncSession, auction_id: int) -> tuple[AuctionBid | None, User | None]:
    row = (
        await session.execute(
            select(AuctionBid, User)
            .join(User, User.id == AuctionBid.user_id)
            .where(AuctionBid.auction_id == auction_id, AuctionBid.status == "active")
            .order_by(AuctionBid.amount.desc(), AuctionBid.created_at.asc())
            .limit(1)
        )
    ).first()
    return row if row else (None, None)


def is_open(auction: Auction, now: datetime | None = None) -> bool:
    current = now or datetime.now(timezone.utc)
    return auction.status == "active" and as_utc(auction.starts_at) <= current < as_utc(auction.ends_at)


def next_minimum_bid(auction: Auction, top_amount: int) -> int:
    """Mirrors the bot's own `max(auction.minimum_bid, top + auction.bid_step
    if top else auction.minimum_bid)` exactly."""
    return max(auction.minimum_bid, top_amount + auction.bid_step if top_amount else auction.minimum_bid)


async def list_active_auctions(session: AsyncSession) -> list[Auction]:
    now = datetime.now(timezone.utc)
    return list(
        (
            await session.scalars(
                select(Auction)
                .where(Auction.status == "active", Auction.starts_at <= now, Auction.ends_at > now)
                .order_by(Auction.ends_at)
            )
        ).all()
    )


async def list_all_auctions(session: AsyncSession) -> list[Auction]:
    return list((await session.scalars(select(Auction).order_by(Auction.created_at.desc()))).all())


async def get_user_bid(session: AsyncSession, auction_id: int, user_id: int) -> AuctionBid | None:
    return await session.scalar(
        select(AuctionBid).where(AuctionBid.auction_id == auction_id, AuctionBid.user_id == user_id)
    )


async def list_bids(session: AsyncSession, auction_id: int) -> list[tuple[AuctionBid, User]]:
    result = await session.execute(
        select(AuctionBid, User)
        .join(User, User.id == AuctionBid.user_id)
        .where(AuctionBid.auction_id == auction_id, AuctionBid.status == "active")
        .order_by(AuctionBid.amount.desc(), AuctionBid.created_at)
    )
    return list(result.all())


async def place_bid(session: AsyncSession, auction: Auction, user: User, amount: int) -> AuctionBid:
    """Mirrors app/handlers/participant/auction_block17.py::auction_bid_save
    exactly — same minimum-bid and balance checks, same upsert-by-user
    semantics (one row per user per auction, re-bidding updates it and
    clears any earlier win/selection markers). Points are never touched
    here; only a confirmed win moves points (see confirm_winner)."""
    if not is_open(auction):
        raise ValueError(BID_ERROR_CLOSED)
    top_bid, _ = await top_bid_with_user(session, auction.id)
    minimum = next_minimum_bid(auction, top_bid.amount if top_bid else 0)
    if amount < minimum:
        raise ValueError(BID_ERROR_BELOW_MINIMUM)
    balance = await total_points(session, user.id)
    if balance < amount:
        raise ValueError(BID_ERROR_INSUFFICIENT_POINTS)
    existing = await get_user_bid(session, auction.id, user.id)
    if existing:
        existing.amount = amount
        existing.status = "active"
        existing.selected_by = None
        existing.selected_at = None
        bid = existing
    else:
        bid = AuctionBid(auction_id=auction.id, user_id=user.id, amount=amount, status="active")
        session.add(bid)
    await session.flush()
    return bid


async def create_auction(
    session: AsyncSession,
    *,
    title: str,
    description: str,
    minimum_bid: int,
    bid_step: int,
    ends_at: datetime,
    created_by_id: int | None,
) -> Auction:
    now = datetime.now(timezone.utc)
    auction = Auction(
        title=title,
        description=description,
        audience_filter_json={},
        starts_at=now,
        ends_at=ends_at,
        minimum_bid=minimum_bid,
        bid_step=bid_step,
        winner_count=1,
        status="active",
        created_by=created_by_id,
    )
    session.add(auction)
    await session.flush()
    return auction


async def confirm_winner(
    session: AsyncSession, auction: Auction, *, actor_id: int | None
) -> tuple[AuctionBid, User] | None:
    """Mirrors app/handlers/admin/auction_block17.py::confirm_winner exactly:
    walks bids highest-first, skips (marks invalid) any bidder who's since
    been blocked/archived or can no longer cover their own bid, deducts
    points only from the actual winner, marks every other active bid
    "lost", and closes the auction. Returns None if no bidder qualifies —
    caller decides what to tell the admin in that case."""
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
    for bid in bids:
        candidate = await session.get(User, bid.user_id)
        if (
            not candidate
            or candidate.is_blocked
            or candidate.is_archived
            or await total_points(session, bid.user_id) < bid.amount
        ):
            bid.status = "invalid"
            continue
        await add_points(
            session,
            user_id=candidate.id,
            points=-bid.amount,
            reason=f"Победа в аукционе: {auction.title}",
            approved_by=actor_id,
            source_type="auction_win",
            source_id=bid.id,
            idempotency_key=f"auction_win:{auction.id}:{bid.id}",
        )
        bid.status = "winner"
        bid.selected_by = actor_id
        bid.selected_at = datetime.now(timezone.utc)
        for other in bids:
            if other.id != bid.id and other.status == "active":
                other.status = "lost"
        auction.status = "completed"
        await session.flush()
        return bid, candidate
    await session.flush()
    return None


async def mark_delivered(session: AsyncSession, auction: Auction) -> User | None:
    winner_bid = await session.scalar(
        select(AuctionBid).where(AuctionBid.auction_id == auction.id, AuctionBid.status == "winner")
    )
    winner = await session.get(User, winner_bid.user_id) if winner_bid else None
    auction.status = "delivered"
    await session.flush()
    return winner


async def cancel_auction(session: AsyncSession, auction: Auction, *, actor_id: int | None) -> None:
    auction.status = "cancelled"
    bids = list(
        (
            await session.scalars(
                select(AuctionBid).where(AuctionBid.auction_id == auction.id, AuctionBid.status == "active")
            )
        ).all()
    )
    for bid in bids:
        bid.status = "cancelled"
    await audit(
        session,
        actor_id=actor_id,
        action="auction.cancelled",
        entity_type="auction",
        entity_id=auction.id,
        old_value={"title": auction.title, "active_bids": len(bids)},
        new_value={"status": "cancelled"},
    )
