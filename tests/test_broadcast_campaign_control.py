from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AuditLog, Broadcast, User
from app.services.admin_broadcast_service import BroadcastError, control_broadcast, resume_broadcasts, send_personal_broadcast
from app.utils.constants import ApplicationStatus, Role


class CampaignControlTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='1234567890:test')
        self.calls = []
        self.action, self.at = 'pause', 1
        self.bot = SimpleNamespace(send_message=self.send)
        self.factory_patch = patch('app.services.notification_service._session_factory', return_value=self.sessions)
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        async with self.sessions() as session:
            self.admin = User(telegram_id=11, first_name='Admin', role=Role.ADMIN, application_status=ApplicationStatus.APPROVED)
            self.members = [User(telegram_id=20+i, first_name='Member', application_status=ApplicationStatus.APPROVED) for i in range(2)]
            # Use a participant role audience, keeping the authorized admin out.
            session.add_all([self.admin, *self.members])
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def send(self, chat_id, text, **kwargs):
        self.calls.append(chat_id)
        if len(self.calls) == self.at:
            async with self.sessions() as session:
                campaign = await session.scalar(select(Broadcast))
                await control_broadcast(session, self.settings, actor=await session.get(User, self.admin.id),
                                        campaign_id=campaign.id, action=self.action)
                await session.commit()
        return SimpleNamespace(message_id=len(self.calls))

    async def launch(self):
        async with self.sessions() as session:
            return await send_personal_broadcast(self.bot, session, audience='role', filter_value='participant',
                text='Stable campaign', author_id=self.admin.id, settings=self.settings, campaign_key='confirmation-1')

    async def test_pause_stops_remaining_recipients_and_resume_keeps_delivery_receipts(self):
        await self.launch()
        assert len(self.calls) == 1
        await resume_broadcasts(self.bot, self.settings, self.sessions)
        assert len(self.calls) == 1
        async with self.sessions() as session:
            campaign = await session.scalar(select(Broadcast))
            assert campaign.status == 'paused'
            await control_broadcast(session, self.settings, actor=await session.get(User, self.admin.id),
                                    campaign_id=campaign.id, action='resume')
            await session.commit()
        await resume_broadcasts(self.bot, self.settings, self.sessions)
        await resume_broadcasts(self.bot, self.settings, self.sessions)
        assert len(self.calls) == 2 and len(set(self.calls)) == 2
        async with self.sessions() as session:
            assert (await session.scalar(select(Broadcast))).status == 'sent'

    async def test_cancel_during_last_inflight_delivery_is_not_overwritten_by_completion(self):
        self.action, self.at = 'cancel', 2
        await self.launch()
        async with self.sessions() as session:
            campaign = await session.scalar(select(Broadcast))
            assert campaign.status == 'cancelled'
        await resume_broadcasts(self.bot, self.settings, self.sessions)
        assert len(self.calls) == 2

    async def test_member_cannot_control_campaign_and_cancel_is_terminal_and_idempotent(self):
        await self.launch()
        async with self.sessions() as session:
            campaign = await session.scalar(select(Broadcast))
            with self.assertRaises(BroadcastError) as denied:
                await control_broadcast(session, self.settings, actor=await session.get(User, self.members[0].id),
                                        campaign_id=campaign.id, action='resume')
            assert denied.exception.code == 'admin_access_required'
            admin = await session.get(User, self.admin.id)
            for _ in range(2):
                await control_broadcast(session, self.settings, actor=admin, campaign_id=campaign.id, action='cancel')
            with self.assertRaises(BroadcastError):
                await control_broadcast(session, self.settings, actor=admin, campaign_id=campaign.id, action='resume')
            await session.commit()
            assert await session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'broadcast.cancel')) == 1
        await resume_broadcasts(self.bot, self.settings, self.sessions)
        assert len(self.calls) == 1

    async def test_pause_on_last_private_message_prevents_public_chat_post(self):
        self.settings.general_chat_id = -100123
        self.at = 3  # all audience also contains the administrator
        with patch('app.services.admin_broadcast_service.send_general_topic', AsyncMock()) as public:
            async with self.sessions() as session:
                await send_personal_broadcast(self.bot, session, audience='all', filter_value=None,
                    text='Stable campaign', author_id=self.admin.id, settings=self.settings, campaign_key='all-confirmation')
            public.assert_not_awaited()
