from __future__ import annotations

import unittest
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import Office, PermissionGrant, User, UserOffice
from app.services import leadership_permission_service as svc


def _settings() -> Settings:
    return Settings(bot_token="x" * 20)


class LeadershipPermissionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = _settings()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int, **overrides) -> User:
        defaults = dict(telegram_id=telegram_id, first_name=f"U{telegram_id}")
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def test_backfilled_office_grants_nothing(self) -> None:
        """ToR section 99: offices without an explicit permission_template
        stay non-elevated even once someone is appointed."""
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            office = Office(title="Legacy office")  # permission_template defaults to []
            session.add(office)
            await session.flush()
            session.add(UserOffice(office_id=office.id, user_id=target.id, appointed_by=admin.id))
            await session.flush()
            await session.refresh(target, attribute_names=["office_assignments", "permission_grants"])

            allowed = await svc.has_scoped_permission(
                session, target, self.settings, target.telegram_id, "clubs.manage"
            )
            self.assertFalse(allowed)

    async def test_office_permission_template_grants_scoped_permission(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            office = Office(
                title="Лидер Медиа",
                scope_type="direction",
                direction_id=42,
                permission_template=["clubs.manage"],
            )
            session.add(office)
            await session.flush()
            session.add(UserOffice(office_id=office.id, user_id=target.id, appointed_by=admin.id))
            await session.flush()
            await session.refresh(target, attribute_names=["office_assignments", "permission_grants"])

            # In-scope: allowed.
            self.assertTrue(
                await svc.has_scoped_permission(
                    session,
                    target,
                    self.settings,
                    target.telegram_id,
                    "clubs.manage",
                    scope_type="direction",
                    scope_id=42,
                )
            )
            # Out-of-scope (different direction): denied.
            self.assertFalse(
                await svc.has_scoped_permission(
                    session,
                    target,
                    self.settings,
                    target.telegram_id,
                    "clubs.manage",
                    scope_type="direction",
                    scope_id=99,
                )
            )
            # No permission for this string at all: denied.
            self.assertFalse(
                await svc.has_scoped_permission(
                    session, target, self.settings, target.telegram_id, "partners.manage"
                )
            )

    async def test_per_assignment_scope_override(self) -> None:
        """ToR section 15: a generic 'Руководитель проекта' office scoped
        per-assignment to a specific project."""
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            office = Office(title="Руководитель проекта", permission_template=["projects.manage"])
            session.add(office)
            await session.flush()
            session.add(
                UserOffice(
                    office_id=office.id,
                    user_id=target.id,
                    appointed_by=admin.id,
                    scope_type="project",
                    scope_id=128,
                )
            )
            await session.flush()
            await session.refresh(target, attribute_names=["office_assignments", "permission_grants"])

            self.assertTrue(
                await svc.has_scoped_permission(
                    session,
                    target,
                    self.settings,
                    target.telegram_id,
                    "projects.manage",
                    scope_type="project",
                    scope_id=128,
                )
            )
            self.assertFalse(
                await svc.has_scoped_permission(
                    session,
                    target,
                    self.settings,
                    target.telegram_id,
                    "projects.manage",
                    scope_type="project",
                    scope_id=999,
                )
            )

    async def test_expired_assignment_denied(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            office = Office(title="И.о. лидера", permission_template=["tasks.manage"])
            session.add(office)
            await session.flush()
            session.add(
                UserOffice(
                    office_id=office.id,
                    user_id=target.id,
                    appointed_by=admin.id,
                    starts_at=date.today() - timedelta(days=30),
                    ends_at=date.today() - timedelta(days=1),
                )
            )
            await session.flush()
            await session.refresh(target, attribute_names=["office_assignments", "permission_grants"])

            self.assertFalse(
                await svc.has_scoped_permission(
                    session, target, self.settings, target.telegram_id, "tasks.manage"
                )
            )

    async def test_not_yet_started_assignment_denied(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            office = Office(title="Будущий лидер", permission_template=["tasks.manage"])
            session.add(office)
            await session.flush()
            session.add(
                UserOffice(
                    office_id=office.id,
                    user_id=target.id,
                    appointed_by=admin.id,
                    starts_at=date.today() + timedelta(days=5),
                )
            )
            await session.flush()
            await session.refresh(target, attribute_names=["office_assignments", "permission_grants"])

            self.assertFalse(
                await svc.has_scoped_permission(
                    session, target, self.settings, target.telegram_id, "tasks.manage"
                )
            )

    async def test_manual_permission_grant_still_works(self) -> None:
        """ToR section 16: PermissionGrant stays a valid manual escape hatch
        alongside office-derived permissions."""
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            session.add(
                PermissionGrant(
                    user_id=target.id, permission="partners.manage", granted_by=admin.id
                )
            )
            await session.flush()
            await session.refresh(target, attribute_names=["permission_grants"])

            self.assertTrue(
                await svc.has_scoped_permission(
                    session, target, self.settings, target.telegram_id, "partners.manage"
                )
            )

    async def test_revoked_grant_denied(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            session.add(
                PermissionGrant(
                    user_id=target.id,
                    permission="partners.manage",
                    granted_by=admin.id,
                    is_active=False,
                )
            )
            await session.flush()
            await session.refresh(target, attribute_names=["permission_grants"])

            self.assertFalse(
                await svc.has_scoped_permission(
                    session, target, self.settings, target.telegram_id, "partners.manage"
                )
            )

    async def test_multiple_assignments_union_their_own_scopes(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            office_a = Office(
                title="Лидер Медиа", direction_id=1, permission_template=["clubs.manage"]
            )
            office_b = Office(
                title="Лидер Дебатов", direction_id=2, permission_template=["clubs.manage"]
            )
            session.add_all([office_a, office_b])
            await session.flush()
            session.add_all(
                [
                    UserOffice(office_id=office_a.id, user_id=target.id, appointed_by=admin.id),
                    UserOffice(office_id=office_b.id, user_id=target.id, appointed_by=admin.id),
                ]
            )
            await session.flush()
            await session.refresh(target, attribute_names=["office_assignments", "permission_grants"])

            for direction_id in (1, 2):
                self.assertTrue(
                    await svc.has_scoped_permission(
                        session,
                        target,
                        self.settings,
                        target.telegram_id,
                        "clubs.manage",
                        scope_type="direction",
                        scope_id=direction_id,
                    )
                )
            self.assertFalse(
                await svc.has_scoped_permission(
                    session,
                    target,
                    self.settings,
                    target.telegram_id,
                    "clubs.manage",
                    scope_type="direction",
                    scope_id=3,
                )
            )

    async def test_admin_bypasses_scope(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 999999, role="admin")
            settings = Settings(bot_token="x" * 20, admin_ids=[999999])
            self.assertTrue(
                await svc.has_scoped_permission(
                    session,
                    admin,
                    settings,
                    999999,
                    "clubs.manage",
                    scope_type="direction",
                    scope_id=1,
                )
            )

    async def test_ended_assignment_flag_denied_even_within_dates(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            office = Office(title="Лидер", permission_template=["tasks.manage"])
            session.add(office)
            await session.flush()
            session.add(
                UserOffice(
                    office_id=office.id, user_id=target.id, appointed_by=admin.id, is_active=False
                )
            )
            await session.flush()
            await session.refresh(target, attribute_names=["office_assignments", "permission_grants"])

            self.assertFalse(
                await svc.has_scoped_permission(
                    session, target, self.settings, target.telegram_id, "tasks.manage"
                )
            )

    async def test_detect_appointment_conflicts_warns_past_threshold(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            offices = [
                Office(title=f"Office {i}", permission_template=["tasks.manage"]) for i in range(3)
            ]
            session.add_all(offices)
            await session.flush()
            for office in offices:
                session.add(
                    UserOffice(office_id=office.id, user_id=target.id, appointed_by=admin.id)
                )
            await session.flush()

            warnings = await svc.detect_appointment_conflicts(session, target.id)
            self.assertEqual(len(warnings), 1)
            self.assertIn("3", warnings[0])

    async def test_detect_appointment_conflicts_silent_below_threshold(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            office = Office(title="Office", permission_template=["tasks.manage"])
            session.add(office)
            await session.flush()
            session.add(UserOffice(office_id=office.id, user_id=target.id, appointed_by=admin.id))
            await session.flush()

            self.assertEqual(await svc.detect_appointment_conflicts(session, target.id), [])

    async def test_decorative_offices_excluded_from_conflict_count(self) -> None:
        """Offices with an empty permission_template (e.g. purely honorary
        directory titles) shouldn't count toward the leadership-load warning."""
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            target = await self._make_user(session, 2)
            offices = [Office(title=f"Honorary {i}") for i in range(3)]
            session.add_all(offices)
            await session.flush()
            for office in offices:
                session.add(
                    UserOffice(office_id=office.id, user_id=target.id, appointed_by=admin.id)
                )
            await session.flush()

            self.assertEqual(await svc.detect_appointment_conflicts(session, target.id), [])


if __name__ == "__main__":
    unittest.main()
