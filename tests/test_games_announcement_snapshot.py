"""Database-backed launch replays never rewrite historical receipts or copy."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.system_models import NotificationDelivery
from app.services.games_launch_service import _send_announcement_once
from app.services.notification_service import _payload_hash


class AnnouncementSnapshotTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = SimpleNamespace(general_chat_id=-100123)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def receipt(self, status, chat_id=-100123):
        async with self.factory() as session:
            session.add(NotificationDelivery(delivery_key='general-topic:notifications:launch',
                chat_id=chat_id, notification_type='general_notifications', status=status,
                payload_hash=_payload_hash('old copy')))
            await session.commit()

    async def send(self, text='new copy'):
        return await _send_announcement_once(object(), self.settings, self.factory,
            'notifications', text, delivery_key='launch')

    async def test_sent_legacy_copy_is_not_resent_or_rewritten(self):
        await self.receipt('sent')
        with patch('app.services.games_launch_service.send_general_topic', new_callable=AsyncMock) as send:
            self.assertTrue(await self.send())
            send.assert_not_awaited()
        async with self.factory() as session:
            row = await session.scalar(select(NotificationDelivery))
            self.assertEqual(row.payload_hash, _payload_hash('old copy'))

    async def test_uncertain_and_changed_recipient_stop(self):
        await self.receipt('uncertain')
        with patch('app.services.games_launch_service.send_general_topic', new_callable=AsyncMock) as send:
            self.assertFalse(await self.send())
            send.assert_not_awaited()
        self.settings.general_chat_id = -100999
        with patch('app.services.games_launch_service.send_general_topic', new_callable=AsyncMock) as send:
            self.assertFalse(await self.send())
            send.assert_not_awaited()

    async def test_retry_uses_frozen_first_copy(self):
        with patch('app.services.games_launch_service.send_general_topic', new=AsyncMock(return_value=False)) as send:
            await self.send('first copy')
            await self.send('edited copy')
            self.assertEqual([call.args[3] for call in send.await_args_list], ['first copy', 'first copy'])

    async def test_unsent_legacy_conflict_needs_reconciliation(self):
        await self.receipt('failed')
        with patch('app.services.games_launch_service.send_general_topic', new_callable=AsyncMock) as send:
            self.assertFalse(await self.send())
            send.assert_not_awaited()
