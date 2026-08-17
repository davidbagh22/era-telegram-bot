"""Points/Ranks ToR phase 1: My Vector actions must award digital-engagement
points through app.services.digital_engagement_service, and only that --
never checkin content. See tests/test_digital_engagement_service.py for the
cap/idempotency logic itself; these tests only check the wiring."""

from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.development_models import DevelopmentGoal, MonthlyCheckin
from app.database.models import User
from app.services.development_service import (
    checkin_questions,
    complete_checkin,
    create_goal,
    review_goal,
    save_weekly_pulse,
)
from app.services.points_service import total_points


class DevelopmentPointsWiringTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int = 1) -> User:
        user = User(telegram_id=telegram_id, first_name="Dev")
        session.add(user)
        await session.flush()
        return user

    async def test_completing_checkin_awards_thirty_points_once(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            checkin = MonthlyCheckin(user_id=user.id, month="2026-08", status="in_progress")
            session.add(checkin)
            await session.flush()

            questions = await checkin_questions(session, user.id, checkin)
            checkin.answers_json = {
                **checkin.answers_json,
                **{q["code"]: 2 for q in questions},
            }
            await session.flush()

            await complete_checkin(session, checkin)
            self.assertEqual(checkin.status, "completed")
            self.assertEqual(await total_points(session, user.id), 30)

            # Already completed -- calling again must not re-award.
            await complete_checkin(session, checkin)
            self.assertEqual(await total_points(session, user.id), 30)

    async def test_setting_a_goal_awards_fifteen_points(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            await create_goal(session, user.id, "Пройти курс", None, None, True)
            self.assertEqual(await total_points(session, user.id), 15)

    async def test_reviewing_goal_as_done_awards_twenty_five_points(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            goal = await create_goal(session, user.id, "Пройти курс", None, None, True)
            # Setting the goal already paid 15; isolate the completion award.
            baseline = await total_points(session, user.id)
            await review_goal(session, user.id, goal.id, "done", None, None)
            self.assertEqual(await total_points(session, user.id) - baseline, 25)

    async def test_reviewing_goal_as_not_done_awards_nothing(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            goal = await create_goal(session, user.id, "Пройти курс", None, None, True)
            baseline = await total_points(session, user.id)
            await review_goal(session, user.id, goal.id, "not_done", None, None)
            self.assertEqual(await total_points(session, user.id), baseline)

    async def test_weekly_pulse_awards_ten_points(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            await save_weekly_pulse(session, user.id, 1)
            self.assertEqual(await total_points(session, user.id), 10)

            # Same week, updated energy: idempotent, no extra points.
            await save_weekly_pulse(session, user.id, 2)
            self.assertEqual(await total_points(session, user.id), 10)


if __name__ == "__main__":
    unittest.main()
