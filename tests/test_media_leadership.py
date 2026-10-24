from unittest import IsolatedAsyncioTestCase

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting, Department, Direction, User
from app.services import media_leadership_service as leadership, media_service


class MediaLeadershipTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def seed(self, session):
        chair = User(telegram_id=101, first_name="Председатель", role="admin", application_status="approved")
        admin = User(telegram_id=102, first_name="Администратор", role="admin", application_status="approved")
        first = User(telegram_id=103, first_name="Первый", application_status="approved")
        second = User(telegram_id=104, first_name="Второй", application_status="approved")
        department = Department(name="Внешние связи")
        session.add_all([chair, admin, first, second, department])
        await session.flush()
        session.add(Direction(name="Медиа", department_id=department.id))
        await session.flush()
        settings = Settings(bot_token="1234567890:test-token", era_chair_user_id=chair.id,
                            media_manager_ids=[first.telegram_id, admin.telegram_id])
        return chair, admin, first, second, settings

    async def test_only_chair_can_appoint_replace_remove_and_revocation_is_immediate(self):
        async with self.factory() as session:
            chair, admin, first, second, settings = await self.seed(session)
            with self.assertRaisesRegex(ValueError, "media_chair_required"):
                await leadership.change_leader(session, admin, settings, target_telegram_id=103, expected_revision=0)
            self.assertFalse(await media_service.can_manage_media(session, admin, settings))
            self.assertFalse(await media_service.can_manage_media(session, first, settings))
            await leadership.change_leader(session, chair, settings, target_telegram_id=103, expected_revision=0)
            self.assertEqual(await media_service.media_access_level(session, first, settings), "leader")
            with self.assertRaisesRegex(ValueError, "media_chair_required"):
                await leadership.change_leader(session, first, settings, target_telegram_id=104, expected_revision=0)
            _, revision = await leadership.leadership_state(session)
            await leadership.change_leader(session, chair, settings, target_telegram_id=104, expected_revision=revision)
            self.assertFalse(await media_service.can_manage_media(session, first, settings))
            self.assertTrue(await media_service.can_manage_media(session, second, settings))
            with self.assertRaisesRegex(ValueError, "media_leader_stale_confirmation"):
                await leadership.change_leader(session, chair, settings, target_telegram_id=103, expected_revision=revision)
            _, revision = await leadership.leadership_state(session)
            await leadership.change_leader(session, chair, settings, target_telegram_id=None, expected_revision=revision)
            self.assertFalse(await media_service.can_manage_media(session, second, settings))
            self.assertTrue(await media_service.can_manage_media(session, chair, settings))

    async def test_inactive_or_unregistered_target_cannot_be_appointed(self):
        async with self.factory() as session:
            chair, _, first, _, settings = await self.seed(session)
            for field, value in [("is_blocked", True), ("is_archived", True), ("application_status", "pending")]:
                original = getattr(first, field)
                setattr(first, field, value)
                await session.flush()
                with self.assertRaisesRegex(ValueError, "media_registered_active_target_required"):
                    await leadership.change_leader(session, chair, settings, target_telegram_id=103, expected_revision=0)
                setattr(first, field, original)
            with self.assertRaisesRegex(ValueError, "media_registered_active_target_required"):
                await leadership.change_leader(session, chair, settings, target_telegram_id=999, expected_revision=0)

    async def test_invitation_can_only_be_disabled_by_current_active_chair(self):
        async with self.factory() as session:
            chair, admin, _, _, settings = await self.seed(session)
            with self.assertRaisesRegex(ValueError, "media_chair_required"):
                await leadership.set_invitation(session, admin, settings, enabled=False)
            await leadership.set_invitation(session, chair, settings, enabled=False)
            config = await session.scalar(select(AppSetting).where(AppSetting.key == media_service.MEDIA_SETTINGS_KEY))
            self.assertFalse(config.value["join_enabled"])
            chair.is_blocked = True
            await session.flush()
            with self.assertRaisesRegex(ValueError, "media_chair_required"):
                await leadership.set_invitation(session, chair, settings, enabled=True)
            self.assertFalse(config.value["join_enabled"])

    async def test_chair_authority_is_not_inferred_from_role_or_username(self):
        async with self.factory() as session:
            chair, admin, _, _, settings = await self.seed(session)
            admin.username = "davidbs2"
            self.assertFalse(leadership.is_media_chair(admin, settings))
            self.assertFalse(leadership.is_media_chair(chair, Settings(bot_token="1234567890:test-token")))

    async def test_old_bot_confirmation_cannot_run_after_chair_access_is_revoked(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from app.handlers.media_management import confirm_leader
        async with self.factory() as session:
            chair, _, _, _, settings = await self.seed(session)
            chair.is_blocked = True
            await session.flush()
            call = SimpleNamespace(from_user=SimpleNamespace(id=chair.telegram_id), answer=AsyncMock(),
                                   message=SimpleNamespace(answer=AsyncMock()), data="media:leader:confirm:old")
            state = AsyncMock()
            state.get_data.return_value = {"media_leader_confirmation": "old", "media_leader_target": 103, "media_leader_revision": 0}
            with patch.object(leadership, "change_leader", AsyncMock()) as change:
                await confirm_leader(call, chair, state, session, settings, None)
                change.assert_not_awaited()
                state.get_data.assert_not_awaited()
                state.clear.assert_not_awaited()
