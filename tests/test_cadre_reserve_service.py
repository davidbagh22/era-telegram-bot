from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Office, Task, User, UserOffice
from app.services import position_management_service as svc
from app.utils.constants import TaskStatus


class CadreReserveServiceTests(unittest.IsolatedAsyncioTestCase):
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

    def test_suggested_roles_empty_for_new_summary(self) -> None:
        summary = svc.CandidateSummary(
            completed_projects=0,
            tasks_completed_on_time=0,
            tasks_completed_total=0,
            on_time_rate=None,
            events_attended=0,
            past_offices=0,
        )
        self.assertEqual(svc.suggested_roles(summary), [])

    def test_suggested_roles_curator_threshold(self) -> None:
        summary = svc.CandidateSummary(
            completed_projects=0,
            tasks_completed_on_time=5,
            tasks_completed_total=5,
            on_time_rate=100.0,
            events_attended=0,
            past_offices=0,
        )
        self.assertIn("Куратор", svc.suggested_roles(summary))

    def test_suggested_roles_project_lead_and_leader(self) -> None:
        summary = svc.CandidateSummary(
            completed_projects=2,
            tasks_completed_on_time=0,
            tasks_completed_total=0,
            on_time_rate=None,
            events_attended=0,
            past_offices=1,
        )
        roles = svc.suggested_roles(summary)
        self.assertIn("Руководитель проекта", roles)
        self.assertIn("Лидер", roles)

    async def test_office_history_orders_newest_first(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            user = await self._make_user(session, 2)
            office_a = Office(title="Куратор Медиа")
            office_b = Office(title="Лидер Медиа")
            session.add_all([office_a, office_b])
            await session.flush()
            session.add(UserOffice(office_id=office_a.id, user_id=user.id, appointed_by=admin.id, is_active=False))
            session.add(UserOffice(office_id=office_b.id, user_id=user.id, appointed_by=admin.id, is_active=True))
            await session.flush()

            history = await svc.office_history(session, user.id)
            self.assertEqual(len(history), 2)

    async def test_cadre_reserve_excludes_active_leaders(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            office = Office(title="Лидер", permission_template=["tasks.manage"])
            session.add(office)
            await session.flush()
            session.add(UserOffice(office_id=office.id, user_id=leader.id, appointed_by=admin.id))
            for i in range(5):
                session.add(
                    Task(
                        title=f"T{i}",
                        description="d",
                        assignee_id=leader.id,
                        creator_id=admin.id,
                        deadline=datetime.now(timezone.utc) + timedelta(days=1),
                        status=TaskStatus.COMPLETED,
                    )
                )
            await session.flush()

            reserve = await svc.list_cadre_reserve(session)
            self.assertEqual([e.user_id for e in reserve], [])

    async def test_cadre_reserve_includes_qualifying_non_leader(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            candidate = await self._make_user(session, 2)
            for i in range(5):
                session.add(
                    Task(
                        title=f"T{i}",
                        description="d",
                        assignee_id=candidate.id,
                        creator_id=admin.id,
                        deadline=datetime.now(timezone.utc) + timedelta(days=1),
                        status=TaskStatus.COMPLETED,
                    )
                )
            await session.flush()

            reserve = await svc.list_cadre_reserve(session)
            self.assertEqual([e.user_id for e in reserve], [candidate.id])
            self.assertIn("Куратор", reserve[0].suggested_roles)


if __name__ == "__main__":
    unittest.main()
