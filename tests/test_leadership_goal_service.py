from __future__ import annotations

import unittest
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import User
from app.services import leadership_goal_service as svc
from app.utils.constants import LeadershipGoalStatus


class LeadershipGoalServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int) -> User:
        user = User(telegram_id=telegram_id, first_name=f"U{telegram_id}")
        session.add(user)
        await session.flush()
        return user

    async def test_create_and_list_goals(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            goal = await svc.create_goal(
                session,
                owner_id=user.id,
                created_by=user.id,
                title="300 участников",
                period_start=date(2026, 8, 1),
                period_end=date(2026, 8, 31),
                metric="participants",
                target=300,
            )
            self.assertEqual(goal.status, LeadershipGoalStatus.ACTIVE)
            goals = await svc.list_goals(session, owner_id=user.id)
            self.assertEqual([g.id for g in goals], [goal.id])

    async def test_update_progress_marks_completed_at_target(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            goal = await svc.create_goal(
                session,
                owner_id=user.id,
                created_by=user.id,
                title="10 задач",
                period_start=date.today(),
                period_end=date.today() + timedelta(days=10),
                target=10,
            )
            await svc.update_progress(session, goal, progress=10)
            self.assertEqual(goal.status, LeadershipGoalStatus.COMPLETED)

    async def test_update_progress_marks_overdue_past_deadline(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            goal = await svc.create_goal(
                session,
                owner_id=user.id,
                created_by=user.id,
                title="Просроченная цель",
                period_start=date.today() - timedelta(days=30),
                period_end=date.today() - timedelta(days=1),
                target=10,
            )
            await svc.update_progress(session, goal, progress=3)
            self.assertEqual(goal.status, LeadershipGoalStatus.OVERDUE)

    async def test_progress_ratio(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            goal = await svc.create_goal(
                session,
                owner_id=user.id,
                created_by=user.id,
                title="x",
                period_start=date.today(),
                period_end=date.today() + timedelta(days=1),
                target=200,
            )
            goal.progress = 50
            self.assertEqual(svc.progress_ratio(goal), 25.0)

    async def test_progress_ratio_none_without_target(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            goal = await svc.create_goal(
                session,
                owner_id=user.id,
                created_by=user.id,
                title="x",
                period_start=date.today(),
                period_end=date.today() + timedelta(days=1),
            )
            self.assertIsNone(svc.progress_ratio(goal))


if __name__ == "__main__":
    unittest.main()
