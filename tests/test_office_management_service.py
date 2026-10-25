from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Office, User, UserOffice
from app.services import office_management_service as svc


class OfficeManagementServiceTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_create_and_list_offices(self) -> None:
        async with self.session_factory() as session:
            office = await svc.create_office(session, title="Куратор мероприятий", description="d")
            self.assertIsNotNone(office.id)
            rows = await svc.list_offices(session)
            self.assertEqual([o.id for o in rows], [office.id])

    async def test_list_offices_excludes_inactive_by_default(self) -> None:
        async with self.session_factory() as session:
            active = await svc.create_office(session, title="A", description=None)
            inactive = Office(title="B", is_active=False)
            session.add(inactive)
            await session.flush()

            self.assertEqual([o.id for o in await svc.list_offices(session)], [active.id])
            self.assertEqual(
                {o.id for o in await svc.list_offices(session, include_inactive=True)},
                {active.id, inactive.id},
            )

    async def test_search_assignable_users_by_name_username_and_telegram_id(self) -> None:
        async with self.session_factory() as session:
            await self._make_user(session, 1, first_name="Anna", username="anna_k")
            await self._make_user(session, 2, first_name="Boris")
            await session.flush()

            self.assertEqual(
                {u.telegram_id for u in await svc.search_assignable_users(session, "ann")}, {1}
            )
            self.assertEqual(
                {u.telegram_id for u in await svc.search_assignable_users(session, "anna_k")}, {1}
            )
            self.assertEqual(
                {u.telegram_id for u in await svc.search_assignable_users(session, "2")}, {2}
            )

    async def test_assign_office_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            office = await svc.create_office(session, title="A", description=None)
            await session.flush()

            first = await svc.assign_office(
                session, office_id=office.id, user_id=target.id, appointed_by_id=admin.id
            )
            self.assertIsNotNone(first)

            second = await svc.assign_office(
                session, office_id=office.id, user_id=target.id, appointed_by_id=admin.id
            )
            self.assertIsNone(second)

            rows = await svc.list_assignments(session, office.id)
            self.assertEqual(len(rows), 1)

    async def test_remove_assignment_ends_it(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            office = await svc.create_office(session, title="A", description=None)
            await session.flush()
            assignment = await svc.assign_office(
                session, office_id=office.id, user_id=target.id, appointed_by_id=admin.id
            )
            svc.remove_assignment(assignment)
            self.assertFalse(assignment.is_active)
            self.assertIsNotNone(assignment.ends_at)

            rows = await svc.list_assignments(session, office.id)
            self.assertEqual(rows, [])

    async def test_delete_office_ends_all_assignments(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target_a = await self._make_user(session, 2)
            target_b = await self._make_user(session, 3)
            office = await svc.create_office(session, title="A", description=None)
            await session.flush()
            await svc.assign_office(session, office_id=office.id, user_id=target_a.id, appointed_by_id=admin.id)
            await svc.assign_office(session, office_id=office.id, user_id=target_b.id, appointed_by_id=admin.id)

            ended = await svc.delete_office(session, office, actor_id=admin.id)
            self.assertEqual(ended, 2)
            self.assertFalse(office.is_active)
            self.assertEqual(await svc.list_assignments(session, office.id), [])

    async def test_list_assignments_only_includes_active(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            office = await svc.create_office(session, title="A", description=None)
            await session.flush()
            session.add(
                UserOffice(office_id=office.id, user_id=target.id, appointed_by=admin.id, is_active=False)
            )
            await session.flush()
            self.assertEqual(await svc.list_assignments(session, office.id), [])


if __name__ == "__main__":
    unittest.main()
