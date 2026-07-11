from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Auction, AuctionBid, User


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
