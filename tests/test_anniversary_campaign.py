import hashlib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting, Event, EventRegistration, User
from app.database.event_experience import EventExperience
from app.database.system_models import NotificationDelivery
from app.services import anniversary_campaign_service as campaign
from app.services import notification_service
from app.services.event_service import register_for_event
from app.utils.constants import ApplicationStatus, Role


class CampaignTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.url = 'sqlite+aiosqlite:///' + str(Path(self.tmp.name) / 'test.db')
        self.engine = create_async_engine(self.url)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = SimpleNamespace(anniversary_2026_campaign='publish', database_url=self.url,
            admin_ids=[123], era_channel_id=-1001, general_chat_id=-1002)
        self.bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username='ERA_1bot')),
            get_chat=AsyncMock(return_value=SimpleNamespace(username='era_leaders1', id=-1001)),
            send_photo=AsyncMock(side_effect=[SimpleNamespace(message_id=n) for n in range(1,30)]))
        async with self.factory() as session:
            session.add(User(telegram_id=123, first_name='Owner', role=Role.ADMIN,
                             application_status=ApplicationStatus.APPROVED, is_blocked=False, is_archived=False))
            await session.commit()
        self.topic = patch.object(campaign, 'ensure_topic', AsyncMock(return_value=77))
        self.topic.start()

    async def asyncTearDown(self):
        self.topic.stop()
        await self.engine.dispose()
        notification_service._session_factory.cache_clear()
        self.tmp.cleanup()

    async def test_prepare_idempotent_original_poster_and_exact_schedule(self):
        a = await campaign.prepare_campaign(self.bot, self.settings, self.factory)
        b = await campaign.prepare_campaign(self.bot, self.settings, self.factory)
        self.assertEqual(a, b)
        self.assertEqual(len(a['deliveries']), 18)
        self.assertEqual(len({d['key'] for d in a['deliveries']}), 18)
        self.assertEqual(len(a['dates']), 8)
        for target in a['targets']:
            slots = [d for d in a['deliveries'] if d['name'] == target['name'] and d['slot'] != 'initial']
            self.assertEqual([d['due_at'] for d in slots], list(campaign.DATES))
            for d in slots:
                self.assertEqual(datetime.fromisoformat(d['due_at']).hour, 18)
                self.assertTrue(d['due_at'].endswith('+04:00'))
        async with self.factory() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 1)
            event = await session.get(Event, a['event_id'])
            exp = await session.get(EventExperience, event.id)
            self.assertEqual(hashlib.sha256(exp.poster_bytes).hexdigest(), campaign.POSTER_SHA)
            self.assertEqual(exp.announcement_status, 'not_requested')
            self.assertFalse(exp.broadcast_enabled)
            self.assertEqual(await register_for_event(session, event, event.created_by), (None, 'guest_registration_required'))
            self.assertEqual(await session.scalar(select(func.count()).select_from(EventRegistration)), 0)
        self.bot.send_photo.assert_not_awaited()

    async def test_existing_candidate_stops_without_mutating_or_sending(self):
        a = await campaign.prepare_campaign(self.bot, self.settings, self.factory)
        async with self.factory() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == campaign.KEY))
            await session.delete(row)
            await session.commit()
        with self.assertRaisesRegex(ValueError, 'existing_event_requires_reconciliation'):
            await campaign.prepare_campaign(self.bot, self.settings, self.factory)
        async with self.factory() as session:
            self.assertIsNotNone(await session.get(Event, a['event_id']))
            self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 1)
        self.bot.send_photo.assert_not_awaited()

    async def test_restart_preserves_per_target_receipts_and_future_dates(self):
        with patch.object(notification_service, '_session_factory', return_value=self.factory):
            now = datetime(2026, 11, 14, 18, tzinfo=campaign.TZ)
            await campaign.run_campaign(self.bot, self.settings, self.factory, now=now)
            await campaign.run_campaign(self.bot, self.settings, self.factory, now=now)
            self.assertEqual(self.bot.send_photo.await_count, 4)
            snapshot = await campaign.campaign_snapshot(self.factory)
            self.assertEqual(len(snapshot['receipts']), 4)
            self.assertTrue(all(r['message_id'] and r['status'] == 'sent' for r in snapshot['receipts']))
            for call in self.bot.send_photo.call_args_list:
                self.assertIn(call.args[0], [-1001, -1002])
                self.assertEqual(call.kwargs['reply_markup'].inline_keyboard[0][0].url, campaign.URL)
                if call.args[0] == -1002:
                    self.assertEqual(call.kwargs['message_thread_id'], 77)

    async def test_uncertain_is_never_replayed_and_off_or_expired_never_sends(self):
        with patch.object(notification_service, '_session_factory', return_value=self.factory):
            now = datetime(2026, 11, 14, 18, tzinfo=campaign.TZ)
            await campaign.run_campaign(self.bot, self.settings, self.factory, now=now)
            async with self.factory() as session:
                row = await session.scalar(select(NotificationDelivery).limit(1))
                row.status = 'uncertain'
                row.message_id = None
                await session.commit()
            await campaign.run_campaign(self.bot, self.settings, self.factory, now=now)
            self.assertEqual(self.bot.send_photo.await_count, 4)
            await campaign.run_campaign(self.bot, self.settings, self.factory, now=campaign.STOP)
            self.settings.anniversary_2026_campaign = 'off'
            await campaign.run_campaign(self.bot, self.settings, self.factory, now=now)
            self.assertEqual(self.bot.send_photo.await_count, 4)

    async def test_api_exposes_guest_cta_not_member_registration(self):
        from app.api.v1.events import _to_event_out
        a = await campaign.prepare_campaign(self.bot, self.settings, self.factory)
        async with self.factory() as session:
            event = await session.get(Event, a['event_id'])
            out = await _to_event_out(session, event, None)
            self.assertFalse(out.can_register)
            self.assertEqual(out.registration_url, campaign.URL)
            self.assertIsNotNone(out.poster_url)
