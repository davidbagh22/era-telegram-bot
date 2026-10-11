"""Release acceptance: actual topic transport and durable delivery ledger."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage
from sqlalchemy import select

from app.database.system_models import NotificationDelivery
from app.services.directions_announcement import ANNOUNCEMENT, publish_directions_announcement
from tests.test_general_topics import GeneralTopicsTests


class DirectionsAnnouncementTests(GeneralTopicsTests):
    async def send(self):
        with patch('app.services.general_topics_service._session_factory', return_value=self.sessions), patch('app.services.notification_service._session_factory', return_value=self.sessions):
            return await publish_directions_announcement(self.bot, self.settings)

    async def test_announcement_html_buttons_topic_and_restart(self):
        await self.send()
        # New worker, same persistent ledger.
        replacement = AsyncMock()
        previous = self.bot.send_message
        self.bot.send_message = replacement
        await self.send()
        replacement.assert_not_awaited()
        args, kwargs = previous.call_args
        self.assertEqual(args, (-100123, ANNOUNCEMENT))
        self.assertEqual(kwargs['message_thread_id'], 101)
        self.assertEqual(kwargs['parse_mode'], 'HTML')
        self.assertEqual([r[0].url for r in kwargs['reply_markup'].inline_keyboard], ['https://t.me/+PsEYN685g1w5ZmEy', 'https://t.me/+zV8olVtkdc8yMWVi'])
        async with self.sessions() as session:
            row = await session.scalar(select(NotificationDelivery))
            self.assertEqual(row.delivery_key, 'general-topic:notifications:era-directions-invite-v1')
            self.assertEqual(row.status, 'sent')

    async def test_ambiguous_network_failure_never_replays(self):
        self.bot.send_message.side_effect = TelegramNetworkError(method=SendMessage(chat_id=-100123, text='test'), message='timeout')
        self.assertFalse(await self.send())
        self.assertFalse(await self.send())
        self.bot.send_message.assert_awaited_once()
        async with self.sessions() as session:
            row = await session.scalar(select(NotificationDelivery))
            self.assertEqual(row.status, 'uncertain')

    async def test_expired_claim_after_lost_ack_is_not_replayed(self):
        await self.send()
        async with self.sessions() as session:
            row = await session.scalar(select(NotificationDelivery))
            row.status = 'pending'
            row.last_attempt_at = datetime.now(timezone.utc) - timedelta(hours=1)
            await session.commit()
        self.assertFalse(await self.send())
        self.bot.send_message.assert_awaited_once()

    async def test_explicit_rate_limit_can_retry(self):
        self.bot.send_message.side_effect = [TelegramRetryAfter(method=SendMessage(chat_id=-100123, text='test'), message='rate limited', retry_after=0), SimpleNamespace(message_id=42)]
        self.assertTrue(await self.send())
        self.assertTrue(await self.send())
        self.assertEqual(self.bot.send_message.await_count, 2)
