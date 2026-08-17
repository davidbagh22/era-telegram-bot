from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Office, PositionApplication, User, UserOffice
from app.services import position_management_service as svc
from app.utils.constants import PositionApplicationStatus


class PositionManagementServiceTests(unittest.IsolatedAsyncioTestCase):
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

    async def _open_office(self, session, **overrides) -> Office:
        defaults = dict(title="Лидер Медиа", is_public=True, application_enabled=True)
        defaults.update(overrides)
        office = Office(**defaults)
        session.add(office)
        await session.flush()
        return office

    async def test_list_open_positions_excludes_non_applicable(self) -> None:
        async with self.session_factory() as session:
            open_office = await self._open_office(session)
            await self._open_office(session, title="Closed", application_enabled=False)
            await self._open_office(session, title="Private", is_public=False)
            await self._open_office(
                session,
                title="Past deadline",
                application_deadline=datetime.now(timezone.utc) - timedelta(days=1),
            )

            positions = await svc.list_open_positions(session)
            self.assertEqual([o.id for o in positions], [open_office.id])

    async def test_submit_application_success(self) -> None:
        async with self.session_factory() as session:
            office = await self._open_office(session)
            user = await self._make_user(session, 1)

            application = await svc.submit_application(
                session, office=office, user=user, motivation="Хочу помочь", plan=None, availability="5ч/нед"
            )
            self.assertEqual(application.status, PositionApplicationStatus.SUBMITTED)
            self.assertIsNotNone(application.submitted_at)

    async def test_submit_application_rejects_when_closed(self) -> None:
        async with self.session_factory() as session:
            office = await self._open_office(session, application_enabled=False)
            user = await self._make_user(session, 1)
            with self.assertRaises(svc.PositionError) as ctx:
                await svc.submit_application(
                    session, office=office, user=user, motivation="x", plan=None, availability=None
                )
            self.assertEqual(ctx.exception.code, "applications_closed")

    async def test_submit_application_rejects_duplicate(self) -> None:
        async with self.session_factory() as session:
            office = await self._open_office(session)
            user = await self._make_user(session, 1)
            await svc.submit_application(
                session, office=office, user=user, motivation="x", plan=None, availability=None
            )
            with self.assertRaises(svc.PositionError) as ctx:
                await svc.submit_application(
                    session, office=office, user=user, motivation="x", plan=None, availability=None
                )
            self.assertEqual(ctx.exception.code, "duplicate_application")

    async def test_submit_application_rejects_when_already_appointed(self) -> None:
        async with self.session_factory() as session:
            office = await self._open_office(session)
            admin = await self._make_user(session, 99)
            user = await self._make_user(session, 1)
            session.add(UserOffice(office_id=office.id, user_id=user.id, appointed_by=admin.id))
            await session.flush()
            with self.assertRaises(svc.PositionError) as ctx:
                await svc.submit_application(
                    session, office=office, user=user, motivation="x", plan=None, availability=None
                )
            self.assertEqual(ctx.exception.code, "already_appointed")

    async def test_withdraw_application(self) -> None:
        async with self.session_factory() as session:
            office = await self._open_office(session)
            user = await self._make_user(session, 1)
            application = await svc.submit_application(
                session, office=office, user=user, motivation="x", plan=None, availability=None
            )
            await svc.withdraw_application(session, application, user_id=user.id)
            self.assertEqual(application.status, PositionApplicationStatus.WITHDRAWN)

    async def test_withdraw_application_rejects_other_users(self) -> None:
        async with self.session_factory() as session:
            office = await self._open_office(session)
            user = await self._make_user(session, 1)
            other = await self._make_user(session, 2)
            application = await svc.submit_application(
                session, office=office, user=user, motivation="x", plan=None, availability=None
            )
            with self.assertRaises(PermissionError):
                await svc.withdraw_application(session, application, user_id=other.id)

    async def test_review_then_appoint_flow(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 99)
            office = await self._open_office(session, default_term_days=180, probation_days=30)
            user = await self._make_user(session, 1)
            application = await svc.submit_application(
                session, office=office, user=user, motivation="x", plan=None, availability=None
            )

            await svc.review_application(
                session, application, status=PositionApplicationStatus.APPROVED, reviewer_id=admin.id
            )
            self.assertEqual(application.status, PositionApplicationStatus.APPROVED)

            result = await svc.appoint_from_application(
                session, application, office, appointed_by_id=admin.id
            )
            self.assertEqual(application.status, PositionApplicationStatus.APPOINTED)
            self.assertTrue(result.assignment.is_active)
            self.assertIsNotNone(result.assignment.ends_at)
            self.assertIsNotNone(result.assignment.probation_ends_at)
            self.assertEqual(result.conflict_warnings, [])

    async def test_appoint_twice_raises(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 99)
            office = await self._open_office(session)
            user = await self._make_user(session, 1)
            application = await svc.submit_application(
                session, office=office, user=user, motivation="x", plan=None, availability=None
            )
            await svc.appoint_from_application(session, application, office, appointed_by_id=admin.id)
            with self.assertRaises(svc.PositionError) as ctx:
                await svc.appoint_from_application(session, application, office, appointed_by_id=admin.id)
            self.assertEqual(ctx.exception.code, "already_appointed")

    async def test_end_and_extend_appointment(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 99)
            office = await self._open_office(session)
            user = await self._make_user(session, 1)
            application = await svc.submit_application(
                session, office=office, user=user, motivation="x", plan=None, availability=None
            )
            result = await svc.appoint_from_application(
                session, application, office, appointed_by_id=admin.id
            )

            new_deadline = result.assignment.starts_at + timedelta(days=30)
            await svc.extend_appointment(
                session, result.assignment, new_ends_at=new_deadline, actor_id=admin.id
            )
            self.assertEqual(result.assignment.ends_at, new_deadline)

            await svc.end_appointment(session, result.assignment, ended_by_id=admin.id, reason="term ended")
            self.assertFalse(result.assignment.is_active)
            self.assertEqual(result.assignment.ended_by, admin.id)
            self.assertEqual(result.assignment.end_reason, "term ended")

    async def test_candidate_summary_all_zero_for_new_user(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, 1)
            summary = await svc.candidate_summary(session, user.id)
            self.assertEqual(summary.completed_projects, 0)
            self.assertEqual(summary.tasks_completed_total, 0)
            self.assertIsNone(summary.on_time_rate)


if __name__ == "__main__":
    unittest.main()
