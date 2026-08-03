from __future__ import annotations

import unittest
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import Project, User
from app.services.admin_dashboard_service import dashboard_metrics, has_dashboard_access
from app.utils.constants import ApplicationStatus, ProjectStatus, Role


class HasDashboardAccessTests(unittest.TestCase):
    def _settings(self, admin_ids=()) -> Settings:
        return Settings(bot_token="1234567890:test-token", admin_ids=list(admin_ids))

    def test_admin_id_in_settings_grants_access_even_without_user(self) -> None:
        settings = self._settings(admin_ids=[555])
        self.assertTrue(has_dashboard_access(None, settings, 555))

    def test_admin_role_grants_access(self) -> None:
        user = SimpleNamespace(role=Role.ADMIN, is_blocked=False, is_archived=False, permission_grants=[])
        self.assertTrue(has_dashboard_access(user, self._settings(), 1))

    def test_any_active_permission_grants_access(self) -> None:
        user = SimpleNamespace(
            role="participant",
            is_blocked=False,
            is_archived=False,
            permission_grants=[SimpleNamespace(is_active=True, permission="people.view")],
        )
        self.assertTrue(has_dashboard_access(user, self._settings(), 1))

    def test_inactive_permission_grant_does_not_grant_access(self) -> None:
        user = SimpleNamespace(
            role="participant",
            is_blocked=False,
            is_archived=False,
            permission_grants=[SimpleNamespace(is_active=False, permission="people.view")],
        )
        self.assertFalse(has_dashboard_access(user, self._settings(), 1))

    def test_blocked_user_denied_even_with_permissions(self) -> None:
        user = SimpleNamespace(
            role="participant",
            is_blocked=True,
            is_archived=False,
            permission_grants=[SimpleNamespace(is_active=True, permission="people.view")],
        )
        self.assertFalse(has_dashboard_access(user, self._settings(), 1))

    def test_plain_participant_denied(self) -> None:
        user = SimpleNamespace(role="participant", is_blocked=False, is_archived=False, permission_grants=[])
        self.assertFalse(has_dashboard_access(user, self._settings(), 1))


class DashboardMetricsTests(unittest.IsolatedAsyncioTestCase):
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
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def test_counts_pending_users_and_projects_in_review(self) -> None:
        async with self.session_factory() as session:
            pending_user = await self._make_user(
                session, 1, application_status=ApplicationStatus.PENDING
            )
            await self._make_user(session, 2, application_status=ApplicationStatus.APPROVED)
            session.add(
                Project(
                    author_id=pending_user.id,
                    title="Idea",
                    short_description="d",
                    status=ProjectStatus.INITIAL_REVIEW,
                )
            )
            await session.flush()

            metrics = await dashboard_metrics(session)
            self.assertEqual(metrics.values["users_pending"], 1)
            self.assertEqual(metrics.values["users_approved"], 1)
            self.assertEqual(metrics.values["projects_review"], 1)
            self.assertGreaterEqual(metrics.attention_total, 2)


if __name__ == "__main__":
    unittest.main()
