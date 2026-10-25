from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.database.models import Auction, User
from app.services import auction_service

# Points-based auctions — the participant-facing half of
# app/handlers/participant/auction_block17.py. Distinct from
# /api/v1/opportunities: an offer has a fixed point cost, an auction's
# cost is whatever the winning bid turns out to be, decided only after
# bidding closes.

router = APIRouter(prefix="/auctions", tags=["auctions"])


class AuctionOut(BaseModel):
    id: int
    title: str
    description: str
    top_bid: int | None
    top_bidder: str | None
    my_bid: int | None
    next_minimum_bid: int
    bid_step: int
    ends_at: str
    is_open: bool


async def _to_auction_out(session: AsyncSession, auction: Auction, user: User) -> AuctionOut:
    top_bid, top_user = await auction_service.top_bid_with_user(session, auction.id)
    my_bid = await auction_service.get_user_bid(session, auction.id, user.id)
    return AuctionOut(
        id=auction.id,
        title=auction.title,
        description=auction.description,
        top_bid=top_bid.amount if top_bid else None,
        top_bidder=auction_service.bidder_name(top_user) if top_bid else None,
        my_bid=my_bid.amount if my_bid and my_bid.status == "active" else None,
        next_minimum_bid=auction_service.next_minimum_bid(auction, top_bid.amount if top_bid else 0),
        bid_step=auction.bid_step,
        ends_at=auction.ends_at.isoformat(),
        is_open=auction_service.is_open(auction),
    )


@router.get("", response_model=list[AuctionOut])
async def list_auctions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AuctionOut]:
    auctions = await auction_service.list_active_auctions(session)
    return [await _to_auction_out(session, auction, user) for auction in auctions]


@router.get("/{auction_id}", response_model=AuctionOut)
async def read_auction(
    auction_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AuctionOut:
    auction = await session.get(Auction, auction_id)
    if auction is None:
        raise HTTPException(status_code=404, detail="auction_not_found")
    return await _to_auction_out(session, auction, user)


class BidIn(BaseModel):
    amount: int


@router.post("/{auction_id}/bid", response_model=AuctionOut)
async def place_bid(
    auction_id: int,
    payload: BidIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AuctionOut:
    if payload.amount <= 0:
        raise HTTPException(status_code=422, detail="invalid_amount")
    auction = await session.get(Auction, auction_id)
    if auction is None:
        raise HTTPException(status_code=404, detail="auction_not_found")
    try:
        await auction_service.place_bid(session, auction, user, payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await _to_auction_out(session, auction, user)
