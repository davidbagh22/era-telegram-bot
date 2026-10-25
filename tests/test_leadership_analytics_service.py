from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import (
    LeadershipAttentionItem,
    LeadershipGoal,
    LeadershipReport,
    Office,
    PositionApplication,
    Task,
    User,
    UserOffice,
)
from app.services import admin_analytics_service as svc
from app.utils.constants import AttentionItemStatus, LeadershipGoalStatus, TaskStatus


class LeadershipAnalyticsServiceTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_empty_org_returns_no_fabricated_score(self) -> None:
        async with self.session_factory() as session:
            data = await svc.build_leadership_analytics(session)
            self.assertEqual(data.vacancies_open, 0)
            self.assertEqual(data.active_leaders, 0)
            self.assertIsNone(data.leadership_health_score)

    async def test_vacancies_and_applications_counted(self) -> None:
        async with self.session_factory() as session:
            session.add(Office(title="A", is_active=True, application_enabled=True))
            session.add(Office(title="B", is_active=True, application_enabled=False))
            await session.flush()
            user = await self._make_user(session, 1)
            session.add(PositionApplication(office_id=1, user_id=user.id, status="submitted"))
            session.add(PositionApplication(office_id=1, user_id=user.id, status="approved"))
            await session.flush()

            data = await svc.build_leadership_analytics(session)
            self.assertEqual(data.vacancies_open, 1)
            self.assertEqual(data.applications_by_status.get("submitted"), 1)
            self.assertEqual(data.applications_by_status.get("approved"), 1)

    async def test_active_leaders_excludes_decorative_offices(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            leadership_office = Office(title="Лидер", permission_template=["tasks.manage"])
            honorary_office = Office(title="Почётный")
            session.add_all([leadership_office, honorary_office])
            await session.flush()
            session.add(UserOffice(office_id=leadership_office.id, user_id=leader.id, appointed_by=admin.id))
            session.add(UserOffice(office_id=honorary_office.id, user_id=admin.id, appointed_by=admin.id))
            await session.flush()

            data = await svc.build_leadership_analytics(session)
            self.assertEqual(data.active_leaders, 1)

    async def test_goal_completion_rate(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            session.add(
                LeadershipGoal(
                    owner_id=user.id,
                    created_by=user.id,
                    title="A",
                    period_start=date.today(),
                    period_end=date.today(),
                    status=LeadershipGoalStatus.COMPLETED,
                )
            )
            session.add(
                LeadershipGoal(
                    owner_id=user.id,
                    created_by=user.id,
                    title="B",
                    period_start=date.today(),
                    period_end=date.today(),
                    status=LeadershipGoalStatus.OVERDUE,
                )
            )
            await session.flush()

            data = await svc.build_leadership_analytics(session)
            self.assertEqual(data.goal_completion_rate, 50.0)

    async def test_open_blockers_and_resolution_time(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            created_at = datetime.now(timezone.utc) - timedelta(hours=5)
            resolved = LeadershipAttentionItem(
                type="leader_blocker",
                owner_id=user.id,
                status=AttentionItemStatus.RESOLVED,
                resolved_at=datetime.now(timezone.utc),
            )
            resolved.created_at = created_at
            session.add(resolved)
            session.add(LeadershipAttentionItem(type="leader_blocker", owner_id=user.id, status=AttentionItemStatus.OPEN))
            await session.flush()

            data = await svc.build_leadership_analytics(session)
            self.assertEqual(data.open_blockers, 1)
            self.assertIsNotNone(data.avg_blocker_resolution_hours)

    async def test_leader_workload(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            office = Office(title="Лидер", permission_template=["tasks.manage"])
            session.add(office)
            await session.flush()
            session.add(UserOffice(office_id=office.id, user_id=leader.id, appointed_by=admin.id))
            session.add(
                Task(
                    title="T",
                    description="d",
                    assignee_id=leader.id,
                    creator_id=admin.id,
                    deadline=datetime.now(timezone.utc) - timedelta(days=1),
                    status=TaskStatus.NEW,
                )
            )
            await session.flush()

            data = await svc.build_leader_workload(session, leader.id)
            self.assertEqual(data.assignments, 1)
            self.assertEqual(data.open_tasks, 1)
            self.assertEqual(data.overdue_tasks, 1)

    async def test_leader_effectiveness(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            session.add(
                Task(
                    title="T",
                    description="d",
                    assignee_id=leader.id,
                    creator_id=admin.id,
                    deadline=datetime.now(timezone.utc) + timedelta(days=1),
                    status=TaskStatus.COMPLETED,
                )
            )
            await session.flush()

            data = await svc.build_leader_effectiveness(session, leader.id)
            self.assertEqual(data.tasks_completed, 1)
            self.assertEqual(data.task_completion_rate, 100.0)


if __name__ == "__main__":
    unittest.main()
