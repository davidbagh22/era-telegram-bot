import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting
from app.services.general_topics_service import ensure_topic, send_general_topic, setup_general_topics
from app.services.daily_public_content_service import run_daily_public_content
from app.services.general_chat_content_service import deliver_planned_content


class GeneralTopicsTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token="1234567890:test-token", general_chat_id=-100123, era_channel_id=-100456)
        async with self.sessions() as session:
            session.add(AppSetting(key="general_forum:-100123:announcements", value=json.dumps({"thread_id": 101})))
            await session.commit()
        self.bot = SimpleNamespace(
            get_chat=AsyncMock(return_value=SimpleNamespace(is_forum=True)),
            get_me=AsyncMock(return_value=SimpleNamespace(id=1, username="ERA_1bot")),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator", can_manage_topics=True)),
            create_forum_topic=AsyncMock(return_value=SimpleNamespace(message_thread_id=102)),
            send_message=AsyncMock(),
        )

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_setup_reuses_persisted_topic_ids_after_restart(self):
        first = await setup_general_topics(self.bot, self.settings, self.sessions)
        second = await setup_general_topics(self.bot, self.settings, self.sessions)
        self.assertEqual(first, {"announcements": 101, "notifications": 102})
        self.assertEqual(first, second)
        self.assertEqual(self.bot.create_forum_topic.await_count, 1)
        self.bot.send_message.assert_not_awaited()

    async def test_no_forum_or_permission_never_falls_back_to_general(self):
        self.bot.get_chat.return_value.is_forum = False
        with patch("app.services.general_topics_service._session_factory", return_value=self.sessions):
            self.assertFalse(await send_general_topic(self.bot, self.settings, "notifications", "Hello"))
            self.bot.get_chat.return_value.is_forum = True
            self.bot.get_chat_member.return_value.can_manage_topics = False
            self.assertIsNone(await ensure_topic(self.bot, self.settings, "notifications"))
        self.bot.send_message.assert_not_awaited()
        self.bot.create_forum_topic.assert_not_awaited()

    async def test_ambiguous_creation_keeps_claim_and_never_retries(self):
        # Telegram may have created a real topic before its response is lost.
        self.bot.create_forum_topic.side_effect = RuntimeError("timeout after remote create")
        self.assertIsNone(await ensure_topic(
            self.bot, self.settings, "notifications", session_factory=self.sessions))
        self.assertIsNone(await ensure_topic(
            self.bot, self.settings, "notifications", session_factory=self.sessions))
        self.bot.create_forum_topic.assert_awaited_once()
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(
                AppSetting.key == "general_forum:-100123:notifications"))
            self.assertEqual(json.loads(row.value), {"state": "creating"})

    async def test_acknowledgement_commit_failure_does_not_recreate_topic(self):
        # Telegram confirms the topic but the DB acknowledgement is lost.
        real_commit = AsyncSession.commit
        commits = 0

        async def fail_second_commit(session):
            nonlocal commits
            commits += 1
            if commits == 2:
                raise RuntimeError("acknowledgement database outage")
            return await real_commit(session)

        with patch.object(AsyncSession, "commit", new=fail_second_commit):
            self.assertIsNone(await ensure_topic(
                self.bot, self.settings, "notifications", session_factory=self.sessions))
        self.assertIsNone(await ensure_topic(
            self.bot, self.settings, "notifications", session_factory=self.sessions))
        self.bot.create_forum_topic.assert_awaited_once()
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(
                AppSetting.key == "general_forum:-100123:notifications"))
            self.assertEqual(json.loads(row.value), {"state": "creating"})

    async def test_topic_creation_sees_committed_claim_before_api_call(self):
        async def create_after_claim(chat_id, *, name):
            async with self.sessions() as session:
                row = await session.scalar(select(AppSetting).where(
                    AppSetting.key == "general_forum:-100123:notifications"))
                self.assertEqual(json.loads(row.value), {"state": "creating"})
            return SimpleNamespace(message_thread_id=102)

        self.bot.create_forum_topic.side_effect = create_after_claim
        self.assertEqual(await ensure_topic(
            self.bot, self.settings, "notifications", session_factory=self.sessions), 102)
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(
                AppSetting.key == "general_forum:-100123:notifications"))
            self.assertEqual(json.loads(row.value), {
                "thread_id": 102, "name": "Оповещения"})
        self.bot.create_forum_topic.assert_awaited_once()

    async def test_second_worker_during_inflight_create_does_not_duplicate_topic(self):
        # The first worker has committed its claim but Telegram has not replied.
        entered = asyncio.Event()
        release = asyncio.Event()

        async def create_delayed(chat_id, *, name):
            entered.set()
            await release.wait()
            return SimpleNamespace(message_thread_id=102)

        self.bot.create_forum_topic.side_effect = create_delayed
        first = asyncio.create_task(ensure_topic(
            self.bot, self.settings, "notifications", session_factory=self.sessions))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            self.assertIsNone(await ensure_topic(
                self.bot, self.settings, "notifications", session_factory=self.sessions))
            self.bot.create_forum_topic.assert_awaited_once()
            self.assertFalse(first.done())
        finally:
            release.set()
        self.assertEqual(await asyncio.wait_for(first, timeout=5), 102)
        self.assertEqual(await ensure_topic(
            self.bot, self.settings, "notifications", session_factory=self.sessions), 102)
        self.bot.create_forum_topic.assert_awaited_once()

    async def test_failed_claim_commit_never_calls_telegram(self):
        # A DB failure before the durable claim must not start remote creation.
        with patch.object(AsyncSession, "commit", new=AsyncMock(
            side_effect=RuntimeError("claim transaction failed"))):
            self.assertIsNone(await ensure_topic(
                self.bot, self.settings, "notifications", session_factory=self.sessions))
        self.bot.create_forum_topic.assert_not_awaited()
        async with self.sessions() as session:
            self.assertIsNone(await session.scalar(select(AppSetting).where(
                AppSetting.key == "general_forum:-100123:notifications")))
        # A later healthy attempt can create exactly once: no remote call occurred.
        self.assertEqual(await ensure_topic(
            self.bot, self.settings, "notifications", session_factory=self.sessions), 102)
        self.bot.create_forum_topic.assert_awaited_once()

    async def test_durable_delivery_is_threaded_and_not_repeated(self):
        with patch("app.services.general_topics_service._session_factory", return_value=self.sessions), patch("app.services.notification_service._session_factory", return_value=self.sessions):
            self.assertTrue(await send_general_topic(self.bot, self.settings, "announcements", "Event", delivery_key="event:1"))
            self.assertTrue(await send_general_topic(self.bot, self.settings, "announcements", "Event", delivery_key="event:1"))
        self.bot.send_message.assert_awaited_once_with(-100123, "Event", reply_markup=None, message_thread_id=101)

    async def test_missing_events_topic_is_not_recreated(self):
        from sqlalchemy import delete
        async with self.sessions() as session:
            await session.execute(delete(AppSetting))
            await session.commit()
        with patch("app.services.general_topics_service._session_factory", return_value=self.sessions):
            self.assertFalse(await send_general_topic(self.bot, self.settings, "announcements", "Event"))
        self.bot.create_forum_topic.assert_not_awaited()
        self.bot.send_message.assert_not_awaited()

    async def test_invalid_saved_routes_neither_deliver_nor_create_replacement_topics(self):
        async with self.sessions() as session:
            row = AppSetting(key="general_forum:-100123:notifications", value="{}")
            session.add(row)
            await session.commit()
            for value in ("{}", "null", "[]", "{broken", *[
                json.dumps({"thread_id": thread}) for thread in (True, False, 0, -7, 1.5, "-7", "0", "bad")
            ]):
                with self.subTest(value=value):
                    row.value = value
                    await session.commit()
                    with patch("app.services.general_topics_service._session_factory", return_value=self.sessions):
                        self.assertIsNone(await ensure_topic(self.bot, self.settings, "notifications"))
                        self.assertFalse(await send_general_topic(self.bot, self.settings, "notifications", "CI", delivery_key="invalid-route"))
                    await session.refresh(row)
                    self.assertEqual(row.value, value)
        self.bot.get_chat.assert_not_awaited()
        self.bot.create_forum_topic.assert_not_awaited()
        self.bot.send_message.assert_not_awaited()

    async def test_saved_positive_ids_in_json_string_or_object_remain_usable(self):
        async with self.sessions() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == "general_forum:-100123:announcements"))
            for value in ('{"thread_id":101}', '{"thread_id":"101"}', {"thread_id": 101}):
                with self.subTest(value=value):
                    row.value = value
                    await session.commit()
                    self.assertEqual(await ensure_topic(self.bot, self.settings, "announcements", session_factory=self.sessions), 101)
        self.bot.create_forum_topic.assert_not_awaited()

    async def test_daily_content_only_targets_channel(self):
        with patch("app.services.daily_public_content_service.datetime") as clock, patch("app.services.daily_public_content_service.scheduled_minute", return_value=540), patch("app.services.daily_public_content_service._deliver_once", new=AsyncMock()) as deliver:
            clock.now.return_value = datetime(2026, 10, 9, 21, 55)
            await run_daily_public_content(self.bot, self.settings, self.sessions)
            self.assertEqual(deliver.await_count, 1)
            self.assertEqual(deliver.call_args.kwargs["chat_id"], -100456)

    async def test_legacy_manual_and_scheduled_quotes_are_disabled(self):
        planned = SimpleNamespace(item=SimpleNamespace(content_type="morning_quote", content_id="q1"))
        for manual in (False, True):
            result = await deliver_planned_content(self.bot, self.settings, None, planned, now=datetime.now(), manual=manual)
            self.assertEqual(result.status, "disabled")
        self.bot.send_message.assert_not_awaited()
