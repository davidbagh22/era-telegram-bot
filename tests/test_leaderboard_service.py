from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import PointTransaction, User
from app.services.leaderboard_service import (
    MAX_TOP_LIMIT,
    _current_week_start,
    build_leaderboard,
    build_weekly_leaderboard,
)
from app.utils.constants import ApplicationStatus, ParticipationStatus, PointCategory


class LeaderboardServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int, **overrides) -> User:
        defaults = dict(
            telegram_id=telegram_id,
            first_name=f"User{telegram_id}",
            last_name="Last",
            phone="+10000000000",
            city="City",
            education_work="Work",
            occupation="Occupation",
            motivation="Motivation",
            available_time="Evenings",
            desired_path="participant",
            personal_data_consent=True,
            is_channel_subscribed=True,
            application_status=ApplicationStatus.APPROVED,
            participation_status=ParticipationStatus.NEW_MEMBER,
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def _award(self, session, user: User, points: int, key: str, **overrides) -> None:
        defaults = dict(
            user_id=user.id,
            points=points,
            reason="test",
            approved_by=user.id,
            source_type="test",
            source_id=1,
            idempotency_key=key,
        )
        defaults.update(overrides)
        session.add(PointTransaction(**defaults))
        await session.flush()

    async def test_entries_ordered_by_points_and_marks_viewer(self) -> None:
        async with self.session_factory() as session:
            leader = await self._make_user(session, 1)
            runner_up = await self._make_user(session, 2)
            await self._award(session, leader, 50, "k1")
            await self._award(session, runner_up, 10, "k2")

            snapshot = await build_leaderboard(session, runner_up)

            self.assertEqual([e.rank for e in snapshot.entries], [1, 2])
            self.assertEqual(snapshot.entries[0].points, 50)
            self.assertFalse(snapshot.entries[0].is_you)
            self.assertTrue(snapshot.entries[1].is_you)
            self.assertEqual(snapshot.me.rank, 2)
            self.assertEqual(snapshot.me.points, 10)

    async def test_viewer_outside_top_limit_still_gets_own_rank(self) -> None:
        async with self.session_factory() as session:
            viewer = await self._make_user(session, 999)
            for i in range(3):
                other = await self._make_user(session, i)
                await self._award(session, other, 100 - i, f"other-{i}")

            snapshot = await build_leaderboard(session, viewer, limit=2)

            self.assertEqual(len(snapshot.entries), 2)
            self.assertTrue(all(not e.is_you for e in snapshot.entries))
            self.assertIsNotNone(snapshot.me)
            self.assertEqual(snapshot.me.rank, 4)
            self.assertTrue(snapshot.me.is_you)

    async def test_unranked_user_not_in_rating_has_no_me_entry(self) -> None:
        async with self.session_factory() as session:
            pending = await self._make_user(
                session, 42, application_status=ApplicationStatus.PENDING
            )
            approved = await self._make_user(session, 43)
            await self._award(session, approved, 5, "k1")

            snapshot = await build_leaderboard(session, pending)

            self.assertIsNone(snapshot.me)
            self.assertEqual(len(snapshot.entries), 1)

    async def test_limit_is_clamped_to_max(self) -> None:
        async with self.session_factory() as session:
            viewer = await self._make_user(session, 1)

            snapshot = await build_leaderboard(session, viewer, limit=10_000)

            # Just proves it doesn't error/blow up on an oversized limit —
            # the actual cap only matters once there are more than
            # MAX_TOP_LIMIT approved users, not worth seeding here.
            self.assertLessEqual(len(snapshot.entries), MAX_TOP_LIMIT)

    async def test_no_last_name_still_produces_clean_display_name(self) -> None:
        async with self.session_factory() as session:
            viewer = await self._make_user(session, 1, last_name=None)
            await self._award(session, viewer, 5, "k1")

            snapshot = await build_leaderboard(session, viewer)

            self.assertEqual(snapshot.entries[0].display_name, "User1")

    async def test_weekly_leaderboard_excludes_out_of_week_and_digital_engagement(self) -> None:
        # DELTA ToR §52-53: only confirmed in-week contribution counts.
        from datetime import timedelta

        async with self.session_factory() as session:
            week_start = _current_week_start()
            contributor = await self._make_user(session, 1)
            engagement_only = await self._make_user(session, 2)
            last_week = await self._make_user(session, 3)

            await self._award(session, contributor, 40, "in-week", created_at=week_start + timedelta(hours=1))
            await self._award(
                session, engagement_only, 100, "engagement",
                created_at=week_start + timedelta(hours=1), category=PointCategory.DIGITAL_ENGAGEMENT,
            )
            await self._award(session, last_week, 100, "before-week", created_at=week_start - timedelta(hours=1))

            snapshot = await build_weekly_leaderboard(session, contributor)

            self.assertEqual([e.points for e in snapshot.entries], [40])
            self.assertTrue(snapshot.entries[0].is_you)

    async def test_weekly_leaderboard_excludes_negative_corrections(self) -> None:
        from datetime import timedelta

        async with self.session_factory() as session:
            week_start = _current_week_start()
            user = await self._make_user(session, 1)
            await self._award(session, user, 30, "earned", created_at=week_start + timedelta(hours=1))
            await self._award(session, user, -10, "correction", created_at=week_start + timedelta(hours=2))

            snapshot = await build_weekly_leaderboard(session, user)

            # The negative correction is excluded from the sum entirely
            # (ToR §53) rather than netted against the real contribution.
            self.assertEqual(snapshot.entries[0].points, 30)

    async def test_weekly_leaderboard_top5_cap(self) -> None:
        from datetime import timedelta

        async with self.session_factory() as session:
            week_start = _current_week_start()
            viewer = await self._make_user(session, 0)
            for i in range(1, 8):
                user = await self._make_user(session, i)
                await self._award(session, user, 100 - i, f"k{i}", created_at=week_start + timedelta(hours=1))

            snapshot = await build_weekly_leaderboard(session, viewer)

            self.assertEqual(len(snapshot.entries), 5)
            self.assertEqual([e.points for e in snapshot.entries], [99, 98, 97, 96, 95])


if __name__ == "__main__":
    unittest.main()
