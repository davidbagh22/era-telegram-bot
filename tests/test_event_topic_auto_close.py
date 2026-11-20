from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from app.services import event_topic_lifecycle as topics


class EventTopicLifecycleTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.exp = SimpleNamespace(
            topic_close_state="open", topic_close_at=None, topic_closed_at=None,
        )
        self.event = SimpleNamespace(id=42)
        self.record = SimpleNamespace(value={"thread": 26690})
        self.session = SimpleNamespace(
            get=AsyncMock(return_value=self.event),
            scalar=AsyncMock(side_effect=[self.exp, self.record]),
            commit=AsyncMock(),
        )
        self.bot = SimpleNamespace(
            close_forum_topic=AsyncMock(),
            reopen_forum_topic=AsyncMock(),
        )
        self.settings = SimpleNamespace(general_chat_id=-1002973371133)

    async def test_only_bot_owned_thread_can_be_closed(self):
        result = await topics.update_topic_status(
            self.bot, self.settings, self.session, 42, "close"
        )
        self.assertEqual(result.topic_close_state, "closed")
        self.bot.close_forum_topic.assert_awaited_once_with(
            chat_id=-1002973371133, message_thread_id=26690
        )
        self.assertIsNotNone(self.exp.topic_closed_at)
        self.session.commit.assert_awaited_once()

    async def test_reopen_clears_stale_schedule(self):
        self.exp.topic_close_state = "closed"
        self.exp.topic_closed_at = datetime.now(timezone.utc)
        self.exp.topic_close_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        await topics.update_topic_status(self.bot, self.settings, self.session, 42, "reopen")
        self.bot.reopen_forum_topic.assert_awaited_once_with(
            chat_id=-1002973371133, message_thread_id=26690
        )
        self.assertEqual(self.exp.topic_close_state, "open")
        self.assertIsNone(self.exp.topic_close_at)
        self.assertIsNone(self.exp.topic_closed_at)

    async def test_unowned_topic_is_never_closed(self):
        self.record.value = {"thread": 1}
        with self.assertRaises(topics.TopicActionError) as caught:
            await topics.update_topic_status(
                self.bot, self.settings, self.session, 42, "close"
            )
        self.assertEqual(caught.exception.code, "event_topic_not_owned")
        self.bot.close_forum_topic.assert_not_awaited()
        self.session.commit.assert_not_awaited()

    async def test_idempotent_closed_state_does_not_send_duplicate_calls(self):
        self.exp.topic_close_state = "closed"
        await topics.update_topic_status(self.bot, self.settings, self.session, 42, "close")
        self.bot.close_forum_topic.assert_not_awaited()

    def test_naive_admin_time_means_yerevan_not_utc(self):
        when = datetime(2026, 11, 24, 19, 0)
        self.assertEqual(topics.utc_aware(when),
                         datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc))
        self.assertEqual(topics.utc_aware(when.replace(tzinfo=ZoneInfo("Asia/Yerevan"))),
                         datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc))

    async def test_due_worker_closes_only_the_recorded_topic(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=1)
        exp = SimpleNamespace(topic_close_state="open", topic_close_at=old, topic_closed_at=None)
        list_session = SimpleNamespace(
            scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [42])),
        )
        update_session = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(id=42)),
            scalar=AsyncMock(side_effect=[
                exp, exp, SimpleNamespace(value={"thread": 26690}),
            ]),
            commit=AsyncMock(), rollback=AsyncMock(),
        )

        class Context:
            def __init__(self, value):
                self.value = value
            async def __aenter__(self):
                return self.value
            async def __aexit__(self, exc_type, exc, tb):
                return False

        sessions = iter([list_session, update_session])
        factory = lambda: Context(next(sessions))
        await topics.close_due_event_topics(self.bot, self.settings, factory)
        self.bot.close_forum_topic.assert_awaited_once_with(
            chat_id=-1002973371133, message_thread_id=26690
        )
        self.assertEqual(exp.topic_close_state, "closed")
        update_session.commit.assert_awaited_once()
