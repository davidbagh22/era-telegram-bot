from __future__ import annotations

import unittest
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import PointTransaction, User
from app.services.digital_engagement_service import (
    _maybe_award_streak,
    award_daily_open,
    award_event_registration,
    award_goal_completed,
    award_goal_set,
    award_vector_monthly_checkin,
    award_vector_weekly_pulse,
)
from app.services.points_service import add_points, total_points
from app.utils.constants import ApplicationStatus


class DigitalEngagementServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, **overrides) -> User:
        defaults = dict(
            telegram_id=overrides.pop("telegram_id", 1),
            first_name="Dev",
            application_status=ApplicationStatus.APPROVED,
            is_blocked=False,
            is_archived=False,
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def _seed_daily_open(self, session, user_id: int, day: date) -> None:
        """Backdoor into the ledger that mirrors what award_daily_open would
        have written on that day, without depending on wall-clock time."""
        await add_points(
            session,
            user_id=user_id,
            points=5,
            reason="Активность в приложении за день",
            approved_by=user_id,
            source_type="digital_daily_open",
            idempotency_key=f"digital:daily_open:{user_id}:{day.isoformat()}",
        )
        transaction = await session.scalar(
            select(PointTransaction).where(
                PointTransaction.idempotency_key == f"digital:daily_open:{user_id}:{day.isoformat()}"
            )
        )
        transaction.created_at = transaction.created_at.replace(
            year=day.year, month=day.month, day=day.day
        )
        await session.flush()

    # --- daily open + streak -------------------------------------------

    async def test_daily_open_awarded_once_per_day(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            first = await award_daily_open(session, user)
            second = await award_daily_open(session, user)
            self.assertIsNotNone(first)
            self.assertEqual(first.id, second.id)
            self.assertEqual(await total_points(session, user.id), 5)

    async def test_daily_open_skipped_for_unapproved_user(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(
                session, telegram_id=2, application_status=ApplicationStatus.PENDING
            )
            result = await award_daily_open(session, user)
            self.assertIsNone(result)
            self.assertEqual(await total_points(session, user.id), 0)

    async def test_daily_open_skipped_for_blocked_user(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, telegram_id=3, is_blocked=True)
            result = await award_daily_open(session, user)
            self.assertIsNone(result)

    async def test_streak_awarded_on_seventh_consecutive_day(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            today = date.today()
            for offset in range(6, 0, -1):
                await self._seed_daily_open(session, user.id, today - timedelta(days=offset))

            # today's daily_open (via award_daily_open) completes the streak
            await award_daily_open(session, user)

            streak_txn = await session.scalar(
                select(PointTransaction).where(
                    PointTransaction.source_type == "digital_streak_7day",
                    PointTransaction.user_id == user.id,
                )
            )
            self.assertIsNotNone(streak_txn)
            self.assertEqual(streak_txn.points, 20)
            self.assertEqual(await total_points(session, user.id), 5 * 7 + 20)

    async def test_streak_not_awarded_at_six_days(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            today = date.today()
            # 5 seeded days + today = 6 consecutive days, one short of the
            # 7-day threshold.
            for offset in range(5, 0, -1):
                await self._seed_daily_open(session, user.id, today - timedelta(days=offset))

            await award_daily_open(session, user)

            streak_txn = await session.scalar(
                select(PointTransaction).where(
                    PointTransaction.source_type == "digital_streak_7day",
                )
            )
            self.assertIsNone(streak_txn)

    async def test_streak_awards_again_after_second_full_week(self) -> None:
        """Mirrors the real daily cadence -- _maybe_award_streak fires once
        per calendar day the way the middleware hook calls it -- rather than
        jumping straight to day 14, which would only ever see the day-14
        streak length and never catch the day-7 one."""
        async with self.session_factory() as session:
            user = await self._make_user(session)
            today = date.today()
            for offset in range(13, -1, -1):
                day = today - timedelta(days=offset)
                await self._seed_daily_open(session, user.id, day)
                await _maybe_award_streak(session, user, day)

            streak_awards = (
                await session.scalars(
                    select(PointTransaction).where(
                        PointTransaction.source_type == "digital_streak_7day",
                    )
                )
            ).all()
            self.assertEqual({t.points for t in streak_awards}, {20})
            self.assertEqual(len(streak_awards), 2)

    # --- event registration ---------------------------------------------

    async def test_event_registration_bonus_awarded_once_per_event(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            first = await award_event_registration(session, user_id=user.id, event_id=42)
            second = await award_event_registration(session, user_id=user.id, event_id=42)
            self.assertEqual(first.id, second.id)
            self.assertEqual(await total_points(session, user.id), 10)

    async def test_event_registration_bonus_is_per_event(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            await award_event_registration(session, user_id=user.id, event_id=1)
            await award_event_registration(session, user_id=user.id, event_id=2)
            self.assertEqual(await total_points(session, user.id), 20)

    # --- My Vector ---------------------------------------------------------

    async def test_vector_monthly_checkin_capped_at_one_per_month(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            first = await award_vector_monthly_checkin(session, user_id=user.id, month="2026-08")
            second = await award_vector_monthly_checkin(session, user_id=user.id, month="2026-08")
            self.assertEqual(first.id, second.id)
            self.assertEqual(await total_points(session, user.id), 30)

    async def test_vector_monthly_checkin_content_free(self) -> None:
        """The ledger row carries no checkin content -- only reason/source_type."""
        async with self.session_factory() as session:
            user = await self._make_user(session)
            transaction = await award_vector_monthly_checkin(
                session, user_id=user.id, month="2026-08"
            )
            self.assertEqual(transaction.source_type, "digital_vector_checkin")

    async def test_vector_weekly_pulse_capped_at_four_per_month(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            base = date(2026, 8, 3)  # a Monday
            awarded = []
            for week in range(5):
                result = await award_vector_weekly_pulse(
                    session, user_id=user.id, week_start=base + timedelta(weeks=week)
                )
                awarded.append(result)
            self.assertEqual(sum(1 for r in awarded if r is not None), 4)
            self.assertIsNone(awarded[-1])
            self.assertEqual(await total_points(session, user.id), 40)

    async def test_vector_weekly_pulse_idempotent_within_week(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            week_start = date(2026, 8, 3)
            first = await award_vector_weekly_pulse(session, user_id=user.id, week_start=week_start)
            second = await award_vector_weekly_pulse(session, user_id=user.id, week_start=week_start)
            self.assertEqual(first.id, second.id)
            self.assertEqual(await total_points(session, user.id), 10)

    async def test_goal_set_capped_at_two_per_month(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            results = [
                await award_goal_set(session, user_id=user.id, goal_id=goal_id, month="2026-08")
                for goal_id in (1, 2, 3)
            ]
            self.assertEqual(sum(1 for r in results if r is not None), 2)
            self.assertEqual(await total_points(session, user.id), 30)

    async def test_goal_completed_capped_at_two_per_month(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            results = [
                await award_goal_completed(session, user_id=user.id, goal_id=goal_id, month="2026-08")
                for goal_id in (1, 2, 3)
            ]
            self.assertEqual(sum(1 for r in results if r is not None), 2)
            self.assertEqual(await total_points(session, user.id), 50)

    async def test_goal_set_idempotent_per_goal(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            first = await award_goal_set(session, user_id=user.id, goal_id=1, month="2026-08")
            second = await award_goal_set(session, user_id=user.id, goal_id=1, month="2026-08")
            self.assertEqual(first.id, second.id)
            self.assertEqual(await total_points(session, user.id), 15)


if __name__ == "__main__":
    unittest.main()
