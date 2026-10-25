from __future__ import annotations

import unittest
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import LeadershipRecurringTemplate, Office, User, UserOffice
from app.services import leadership_recurring_service as svc


class LeadershipRecurringServiceTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_current_period_monthly(self) -> None:
        start, end = svc.current_period("monthly", today=date(2026, 8, 17))
        self.assertEqual(start, date(2026, 8, 1))
        self.assertEqual(end, date(2026, 8, 31))

    async def test_current_period_weekly(self) -> None:
        start, end = svc.current_period("weekly", today=date(2026, 8, 17))  # Monday
        self.assertEqual(start, date(2026, 8, 17))
        self.assertEqual(end, date(2026, 8, 23))

    async def test_sync_creates_one_task_per_template(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            office = Office(title="Лидер Медиа", permission_template=["clubs.manage"])
            session.add(office)
            await session.flush()
            session.add(
                LeadershipRecurringTemplate(
                    office_id=None, title="Поставить цели месяца", frequency="monthly"
                )
            )
            session.add(
                LeadershipRecurringTemplate(
                    office_id=office.id, title="Провести активности клуба", frequency="monthly"
                )
            )
            await session.flush()
            assignment = UserOffice(office_id=office.id, user_id=leader.id, appointed_by=admin.id)
            session.add(assignment)
            await session.flush()

            created = await svc.sync_recurring_tasks(session, assignment)
            self.assertEqual(len(created), 2)

    async def test_sync_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            office = Office(title="Лидер Медиа", permission_template=["clubs.manage"])
            session.add(office)
            await session.flush()
            session.add(LeadershipRecurringTemplate(office_id=None, title="Цели месяца", frequency="monthly"))
            await session.flush()
            assignment = UserOffice(office_id=office.id, user_id=leader.id, appointed_by=admin.id)
            session.add(assignment)
            await session.flush()

            first = await svc.sync_recurring_tasks(session, assignment)
            second = await svc.sync_recurring_tasks(session, assignment)
            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 0)

    async def test_sync_skips_inactive_templates(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            leader = await self._make_user(session, 2)
            office = Office(title="Лидер Медиа", permission_template=["clubs.manage"])
            session.add(office)
            await session.flush()
            session.add(
                LeadershipRecurringTemplate(
                    office_id=None, title="Отключённый шаблон", frequency="monthly", is_active=False
                )
            )
            await session.flush()
            assignment = UserOffice(office_id=office.id, user_id=leader.id, appointed_by=admin.id)
            session.add(assignment)
            await session.flush()

            created = await svc.sync_recurring_tasks(session, assignment)
            self.assertEqual(created, [])


if __name__ == "__main__":
    unittest.main()
