from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import User
from app.services.application_review_service import (
    approve_application,
    reject_application,
    request_more_info,
)
from app.utils.constants import ApplicationStatus, ParticipationStatus, Role


class ApplicationReviewServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, **overrides) -> User:
        defaults = dict(
            telegram_id=1,
            first_name="Dev",
            last_name=None,
            phone="+10000000000",
            city="City",
            education_work="Work",
            occupation="Occupation",
            motivation="Motivation",
            available_time="Evenings",
            desired_path="participant",
            personal_data_consent=True,
            is_channel_subscribed=True,
            application_status=ApplicationStatus.PENDING,
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def test_approve_sets_role_and_awards_points(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            result = await approve_application(session, user, actor_id=user.id)
            self.assertTrue(result.changed)
            self.assertEqual(user.application_status, ApplicationStatus.APPROVED)
            self.assertEqual(user.role, Role.PARTICIPANT)
            self.assertEqual(user.participation_status, ParticipationStatus.NEW_MEMBER)

    async def test_approve_twice_is_a_no_op(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.APPROVED)
            result = await approve_application(session, user, actor_id=user.id)
            self.assertFalse(result.changed)
            self.assertEqual(result.code, "already_approved")

    async def test_cannot_approve_rejected_application(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.REJECTED)
            result = await approve_application(session, user, actor_id=user.id)
            self.assertFalse(result.changed)
            self.assertEqual(result.code, "already_rejected")

    async def test_reject_sets_status(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            result = await reject_application(session, user, actor_id=user.id, comment="no")
            self.assertTrue(result.changed)
            self.assertEqual(user.application_status, ApplicationStatus.REJECTED)

    async def test_cannot_reject_approved_application(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.APPROVED)
            result = await reject_application(session, user, actor_id=user.id, comment="no")
            self.assertFalse(result.changed)
            self.assertEqual(result.code, "already_approved")

    async def test_request_more_info_sets_needs_info(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            result = await request_more_info(session, user, actor_id=user.id, comment="add phone")
            self.assertTrue(result.changed)
            self.assertEqual(user.application_status, ApplicationStatus.NEEDS_INFO)

    async def test_request_more_info_on_approved_is_a_no_op(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session, application_status=ApplicationStatus.APPROVED)
            result = await request_more_info(session, user, actor_id=user.id, comment="x")
            self.assertFalse(result.changed)
            self.assertEqual(result.code, "already_approved")


if __name__ == "__main__":
    unittest.main()
