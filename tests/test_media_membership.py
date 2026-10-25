from unittest import IsolatedAsyncioTestCase

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting, AuditLog, Department, Direction, PermissionGrant, User, UserDepartment, UserDirection
from app.repositories.users import create_user_from_registration
from app.services.media_membership_service import complete_join, request_join
from app.services.media_service import MEDIA_SETTINGS_KEY, media_access_level


class MediaMembershipTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token="1234567890:test-token")
        async with self.factory() as session:
            department = Department(name="Внешние связи")
            session.add(department)
            await session.flush()
            session.add(Direction(name="Медиа", department_id=department.id))
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_repeated_join_preserves_other_memberships_without_granting_management(self):
        async with self.factory() as session:
            user = User(telegram_id=101, first_name="Участник", application_status="approved")
            other = Department(name="Другой отдел")
            session.add_all([user, other])
            await session.flush()
            direction = Direction(name="Другое направление", department_id=other.id)
            session.add(direction)
            await session.flush()
            session.add_all([UserDepartment(user_id=user.id, department_id=other.id, status="approved"),
                             UserDirection(user_id=user.id, direction_id=direction.id, status="approved")])
            self.assertEqual(await request_join(session, 101, user), "joined")
            self.assertEqual(await request_join(session, 101, user), "already_joined")
            await session.commit()
            self.assertEqual(await session.scalar(select(func.count()).select_from(UserDirection)), 2)
            self.assertEqual(await session.scalar(select(func.count()).select_from(UserDepartment)), 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(PermissionGrant)), 0)
            self.assertEqual(await media_access_level(session, user, self.settings), "member")
            self.assertEqual(await session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "media.member_joined")), 1)

    async def test_new_registration_resumes_durable_intent_and_keeps_approval_gate(self):
        async with self.factory() as session:
            self.assertEqual(await request_join(session, 202, None), "registration_required")
            await session.commit()
        async with self.factory() as session:
            user, created = await create_user_from_registration(session, telegram_id=202, username="new",
                data={"first_name": "Новый", "last_name": "Участник", "age": 20, "departments": [], "directions": []})
            self.assertTrue(created)
            self.assertEqual(await media_access_level(session, user, self.settings), "no_access")
            self.assertEqual(await session.scalar(select(UserDirection.status).where(UserDirection.user_id == user.id)), "approved")
            await session.commit()
            user.application_status = "approved"
            await session.flush()
            self.assertEqual(await media_access_level(session, user, self.settings), "member")
            self.assertEqual(await complete_join(session, user), "already_joined")

    async def test_disabled_invite_cannot_complete_old_intent(self):
        async with self.factory() as session:
            await request_join(session, 303, None)
            session.add(AppSetting(key=MEDIA_SETTINGS_KEY, value={"join_enabled": False}))
            user = User(telegram_id=303, first_name="Новый", application_status="approved")
            session.add(user)
            await session.flush()
            self.assertEqual(await complete_join(session, user), "disabled")
            with self.assertRaisesRegex(ValueError, "media_invitation_disabled"):
                await request_join(session, 303, user)
            self.assertEqual(await session.scalar(select(func.count()).select_from(UserDirection)), 0)

    async def test_blocked_archived_and_identity_substitution_cannot_join(self):
        async with self.factory() as session:
            user = User(telegram_id=404, first_name="Участник", application_status="approved")
            session.add(user)
            await session.flush()
            for field in ["is_blocked", "is_archived"]:
                setattr(user, field, True)
                with self.assertRaisesRegex(ValueError, "media_join_forbidden"):
                    await request_join(session, 404, user)
                setattr(user, field, False)
            with self.assertRaisesRegex(ValueError, "media_join_forbidden"):
                await request_join(session, 999, user)
            self.assertEqual(await session.scalar(select(func.count()).select_from(UserDirection)), 0)
