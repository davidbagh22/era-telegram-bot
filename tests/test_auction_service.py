from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Auction, AuctionBid, PointTransaction, User
from app.services import auction_service as svc


class AuctionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int, **overrides) -> User:
        defaults = dict(telegram_id=telegram_id, first_name=f"U{telegram_id}")
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def _grant_points(self, session, user_id: int, points: int) -> None:
        session.add(
            PointTransaction(
                user_id=user_id,
                points=points,
                reason="test",
                idempotency_key=f"test:{user_id}:{points}:{datetime.now().timestamp()}",
            )
        )
        await session.flush()

    def _auction(self, *, created_by: int, **overrides) -> Auction:
        now = datetime.now(timezone.utc)
        defaults = dict(
            title="Лот",
            description="d",
            audience_filter_json={},
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
            minimum_bid=100,
            bid_step=10,
            winner_count=1,
            status="active",
            created_by=created_by,
        )
        defaults.update(overrides)
        return Auction(**defaults)

    def test_next_minimum_bid_with_and_without_existing_top(self) -> None:
        auction = self._auction(created_by=1, minimum_bid=100, bid_step=10)
        self.assertEqual(svc.next_minimum_bid(auction, 0), 100)
        self.assertEqual(svc.next_minimum_bid(auction, 150), 160)

    async def test_place_bid_rejects_closed_auction(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            bidder = await self._make_user(session, 2)
            auction = self._auction(created_by=admin.id, status="completed")
            session.add(auction)
            await session.flush()
            with self.assertRaises(ValueError) as ctx:
                await svc.place_bid(session, auction, bidder, 100)
            self.assertEqual(str(ctx.exception), svc.BID_ERROR_CLOSED)

    async def test_place_bid_rejects_below_minimum(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            bidder = await self._make_user(session, 2)
            auction = self._auction(created_by=admin.id, minimum_bid=100)
            session.add(auction)
            await session.flush()
            await self._grant_points(session, bidder.id, 1000)
            with self.assertRaises(ValueError) as ctx:
                await svc.place_bid(session, auction, bidder, 50)
            self.assertEqual(str(ctx.exception), svc.BID_ERROR_BELOW_MINIMUM)

    async def test_place_bid_rejects_insufficient_points(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            bidder = await self._make_user(session, 2)
            auction = self._auction(created_by=admin.id, minimum_bid=100)
            session.add(auction)
            await session.flush()
            await self._grant_points(session, bidder.id, 50)
            with self.assertRaises(ValueError) as ctx:
                await svc.place_bid(session, auction, bidder, 100)
            self.assertEqual(str(ctx.exception), svc.BID_ERROR_INSUFFICIENT_POINTS)

    async def test_place_bid_upserts_single_row_per_user(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            bidder = await self._make_user(session, 2)
            auction = self._auction(created_by=admin.id, minimum_bid=100, bid_step=10)
            session.add(auction)
            await session.flush()
            await self._grant_points(session, bidder.id, 1000)

            await svc.place_bid(session, auction, bidder, 100)
            await svc.place_bid(session, auction, bidder, 150)

            bids = list(
                (await session.scalars(select(AuctionBid).where(AuctionBid.auction_id == auction.id))).all()
            )
            self.assertEqual(len(bids), 1)
            self.assertEqual(bids[0].amount, 150)

    async def test_place_bid_enforces_step_over_current_top(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            challenger = await self._make_user(session, 3)
            auction = self._auction(created_by=admin.id, minimum_bid=100, bid_step=10)
            session.add(auction)
            await session.flush()
            await self._grant_points(session, leader.id, 1000)
            await self._grant_points(session, challenger.id, 1000)
            await svc.place_bid(session, auction, leader, 100)

            with self.assertRaises(ValueError):
                await svc.place_bid(session, auction, challenger, 105)  # below 100+10 step

            await svc.place_bid(session, auction, challenger, 110)
            top_bid, top_user = await svc.top_bid_with_user(session, auction.id)
            self.assertEqual(top_bid.amount, 110)
            self.assertEqual(top_user.id, challenger.id)

    async def test_confirm_winner_pays_top_bidder_and_marks_others_lost(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            winner = await self._make_user(session, 2)
            loser = await self._make_user(session, 3)
            auction = self._auction(created_by=admin.id, minimum_bid=100, bid_step=10)
            session.add(auction)
            await session.flush()
            await self._grant_points(session, winner.id, 1000)
            await self._grant_points(session, loser.id, 1000)
            await svc.place_bid(session, auction, loser, 100)
            await svc.place_bid(session, auction, winner, 200)

            result = await svc.confirm_winner(session, auction, actor_id=admin.id)
            self.assertIsNotNone(result)
            bid, candidate = result
            self.assertEqual(candidate.id, winner.id)
            self.assertEqual(bid.status, "winner")
            self.assertEqual(auction.status, "completed")

            loser_bid = await svc.get_user_bid(session, auction.id, loser.id)
            self.assertEqual(loser_bid.status, "lost")

    async def test_confirm_winner_skips_blocked_bidder_and_falls_through(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            blocked = await self._make_user(session, 2, is_blocked=True)
            runner_up = await self._make_user(session, 3)
            auction = self._auction(created_by=admin.id, minimum_bid=100, bid_step=10)
            session.add(auction)
            await session.flush()
            await self._grant_points(session, runner_up.id, 1000)
            # runner_up bids first, while the minimum is still low. blocked's
            # higher bid is inserted directly afterwards (bypassing
            # place_bid, since a real blocked user couldn't place one),
            # simulating someone being blocked after bidding but before the
            # auction closed.
            await svc.place_bid(session, auction, runner_up, 100)
            session.add(AuctionBid(auction_id=auction.id, user_id=blocked.id, amount=500, status="active"))
            await session.flush()

            result = await svc.confirm_winner(session, auction, actor_id=admin.id)
            self.assertIsNotNone(result)
            _, candidate = result
            self.assertEqual(candidate.id, runner_up.id)

            blocked_bid = await svc.get_user_bid(session, auction.id, blocked.id)
            self.assertEqual(blocked_bid.status, "invalid")

    async def test_confirm_winner_returns_none_when_nobody_qualifies(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            blocked = await self._make_user(session, 2, is_blocked=True)
            auction = self._auction(created_by=admin.id)
            session.add(auction)
            await session.flush()
            session.add(AuctionBid(auction_id=auction.id, user_id=blocked.id, amount=500, status="active"))
            await session.flush()

            result = await svc.confirm_winner(session, auction, actor_id=admin.id)
            self.assertIsNone(result)

    async def test_mark_delivered_returns_winner_and_sets_status(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            winner = await self._make_user(session, 2)
            auction = self._auction(created_by=admin.id, status="completed")
            session.add(auction)
            await session.flush()
            session.add(AuctionBid(auction_id=auction.id, user_id=winner.id, amount=200, status="winner"))
            await session.flush()

            result = await svc.mark_delivered(session, auction)
            self.assertEqual(result.id, winner.id)
            self.assertEqual(auction.status, "delivered")

    async def test_cancel_auction_marks_bids_cancelled(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            bidder = await self._make_user(session, 2)
            auction = self._auction(created_by=admin.id, minimum_bid=100)
            session.add(auction)
            await session.flush()
            await self._grant_points(session, bidder.id, 1000)
            await svc.place_bid(session, auction, bidder, 100)

            await svc.cancel_auction(session, auction, actor_id=admin.id)
            self.assertEqual(auction.status, "cancelled")
            bid = await svc.get_user_bid(session, auction.id, bidder.id)
            self.assertEqual(bid.status, "cancelled")


if __name__ == "__main__":
    unittest.main()
