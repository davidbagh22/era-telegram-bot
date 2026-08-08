from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import Badge, PermissionGrant, User
from app.services import user_management_service as svc
from app.utils.constants import ApplicationStatus, Role


class UserManagementServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token="1234567890:test-token", admin_ids=[555])

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int, **overrides) -> User:
        defaults = dict(
            telegram_id=telegram_id,
            first_name="Dev",
            last_name=None,
            username=None,
            role=Role.PARTICIPANT,
            application_status=ApplicationStatus.APPROVED,
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    # -- search_users -----------------------------------------------------

    async def test_search_by_name_and_role_filters(self) -> None:
        async with self.session_factory() as session:
            await self._make_user(session, 1, first_name="Anna", role=Role.PARTICIPANT)
            await self._make_user(session, 2, first_name="Boris", role=Role.LEADER)
            await session.flush()

            rows, total = await svc.search_users(session, query="ann")
            self.assertEqual(total, 1)
            self.assertEqual(rows[0].first_name, "Anna")

            rows, total = await svc.search_users(session, role=Role.LEADER.value)
            self.assertEqual(total, 1)
            self.assertEqual(rows[0].first_name, "Boris")

    async def test_search_excludes_archived_by_default(self) -> None:
        async with self.session_factory() as session:
            await self._make_user(session, 1, is_archived=True)
            await self._make_user(session, 2)
            await session.flush()

            _, total_default = await svc.search_users(session)
            self.assertEqual(total_default, 1)

            _, total_with_archived = await svc.search_users(session, include_archived=True)
            self.assertEqual(total_with_archived, 2)

    async def test_search_by_telegram_id(self) -> None:
        async with self.session_factory() as session:
            await self._make_user(session, 424242)
            await session.flush()
            rows, total = await svc.search_users(session, query="424242")
            self.assertEqual(total, 1)
            self.assertEqual(rows[0].telegram_id, 424242)

    # -- role / block / archive --------------------------------------------

    async def test_change_role_success(self) -> None:
        async with self.session_factory() as session:
            actor = await self._make_user(session, 1, role=Role.ADMIN)
            target = await self._make_user(session, 2, role=Role.PARTICIPANT)
            await session.flush()
            decision = await svc.change_role(
                session,
                actor=actor,
                actor_telegram_id=actor.telegram_id,
                target=target,
                new_role=Role.LEADER,
                settings=self.settings,
            )
            self.assertTrue(decision.allowed)
            self.assertEqual(target.role, Role.LEADER.value)

    async def test_change_role_denied_for_self(self) -> None:
        async with self.session_factory() as session:
            actor = await self._make_user(session, 1, role=Role.ADMIN)
            await session.flush()
            decision = await svc.change_role(
                session,
                actor=actor,
                actor_telegram_id=actor.telegram_id,
                target=actor,
                new_role=Role.PARTICIPANT,
                settings=self.settings,
            )
            self.assertFalse(decision.allowed)
            self.assertEqual(actor.role, Role.ADMIN.value)

    async def test_set_blocked_denied_for_settings_admin(self) -> None:
        async with self.session_factory() as session:
            actor = await self._make_user(session, 1, role=Role.ADMIN)
            target = await self._make_user(session, 555, role=Role.ADMIN)  # in settings.admin_ids
            await session.flush()
            decision = await svc.set_blocked(
                session, actor=actor, target=target, settings=self.settings, blocked=True
            )
            self.assertFalse(decision.allowed)
            self.assertFalse(target.is_blocked)

    async def test_set_blocked_and_unblocked_round_trip(self) -> None:
        async with self.session_factory() as session:
            actor = await self._make_user(session, 1, role=Role.ADMIN)
            target = await self._make_user(session, 2)
            await session.flush()
            await svc.set_blocked(session, actor=actor, target=target, settings=self.settings, blocked=True)
            self.assertTrue(target.is_blocked)
            await svc.set_blocked(session, actor=actor, target=target, settings=self.settings, blocked=False)
            self.assertFalse(target.is_blocked)

    async def test_set_archived_sets_and_clears_metadata(self) -> None:
        async with self.session_factory() as session:
            actor = await self._make_user(session, 1, role=Role.ADMIN)
            target = await self._make_user(session, 2)
            await session.flush()
            await svc.set_archived(session, actor=actor, target=target, settings=self.settings, archived=True)
            self.assertTrue(target.is_archived)
            self.assertIsNotNone(target.archived_at)
            self.assertEqual(target.archived_by, actor.id)

            await svc.set_archived(session, actor=actor, target=target, settings=self.settings, archived=False)
            self.assertFalse(target.is_archived)
            self.assertIsNone(target.archived_at)
            self.assertIsNone(target.archived_by)

    # -- permissions --------------------------------------------------------

    async def test_toggle_permission_creates_then_toggles_existing_grant(self) -> None:
        async with self.session_factory() as session:
            actor = await self._make_user(session, 1, role=Role.ADMIN)
            target = await self._make_user(session, 2)
            await session.flush()

            decision, enabled = await svc.toggle_permission(
                session, actor=actor, target=target, permission="people.view"
            )
            self.assertTrue(decision.allowed)
            self.assertTrue(enabled)

            decision, enabled = await svc.toggle_permission(
                session, actor=actor, target=target, permission="people.view"
            )
            self.assertTrue(decision.allowed)
            self.assertFalse(enabled)

    async def test_toggle_permission_rejects_unknown_permission(self) -> None:
        async with self.session_factory() as session:
            actor = await self._make_user(session, 1, role=Role.ADMIN)
            target = await self._make_user(session, 2)
            await session.flush()
            decision, _ = await svc.toggle_permission(
                session, actor=actor, target=target, permission="not.a.real.permission"
            )
            self.assertFalse(decision.allowed)

    async def test_toggle_permission_denied_for_self(self) -> None:
        async with self.session_factory() as session:
            actor = await self._make_user(session, 1, role=Role.ADMIN)
            await session.flush()
            decision, _ = await svc.toggle_permission(
                session, actor=actor, target=actor, permission="people.view"
            )
            self.assertFalse(decision.allowed)

    # -- points / badges ------------------------------------------------------

    async def test_award_points_updates_balance(self) -> None:
        async with self.session_factory() as session:
            actor = await self._make_user(session, 1, role=Role.ADMIN)
            target = await self._make_user(session, 2)
            await session.flush()
            balance = await svc.award_points(
                session, target=target, amount=50, reason="Тест", approved_by_id=actor.id
            )
            self.assertEqual(balance, 50)
            balance = await svc.award_points(
                session, target=target, amount=-20, reason="Коррекция", approved_by_id=actor.id
            )
            self.assertEqual(balance, 30)

    async def test_award_badge_awards_once_then_no_ops(self) -> None:
        async with self.session_factory() as session:
            actor = await self._make_user(session, 1, role=Role.ADMIN)
            target = await self._make_user(session, 2)
            badge = Badge(name="Первый шаг")
            session.add(badge)
            await session.flush()

            self.assertIn(badge.id, [b.id for b in await svc.available_badges(session, target.id)])
            awarded = await svc.award_badge(
                session, target=target, badge=badge, reason="За старт", awarded_by_id=actor.id
            )
            self.assertTrue(awarded)
            self.assertNotIn(badge.id, [b.id for b in await svc.available_badges(session, target.id)])
            self.assertIn(badge.id, [b.id for b in await svc.user_badges(session, target.id)])

            awarded_again = await svc.award_badge(
                session, target=target, badge=badge, reason="Повторно", awarded_by_id=actor.id
            )
            self.assertFalse(awarded_again)

    async def test_active_permission_set_reflects_only_active_grants(self) -> None:
        async with self.session_factory() as session:
            actor = await self._make_user(session, 1, role=Role.ADMIN)
            target = await self._make_user(session, 2)
            await session.flush()
            session.add(
                PermissionGrant(
                    user_id=target.id,
                    permission="events.manage",
                    granted_by=actor.id,
                    is_active=False,
                )
            )
            session.add(
                PermissionGrant(
                    user_id=target.id,
                    permission="tasks.manage",
                    granted_by=actor.id,
                    is_active=True,
                )
            )
            await session.flush()
            await session.refresh(target, attribute_names=["permission_grants"])
            self.assertEqual(svc.active_permission_set(target), {"tasks.manage"})


if __name__ == "__main__":
    unittest.main()
