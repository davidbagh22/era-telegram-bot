import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import CreateForumTopic, PinChatMessage, ReopenForumTopic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting
from app.services.media_topics_service import TOPICS, bind_topic, delivery_topic, setup_media_topics, topic_links
from app.services.notification_service import NotificationDeliveryResult


class MediaTopicsTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token="1234567890:test-token", media_chat_id=-10012345)
        self.bot = SimpleNamespace(id=42,
            get_chat=AsyncMock(return_value=SimpleNamespace(is_forum=True)),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator", can_manage_topics=True, can_pin_messages=True)),
            create_forum_topic=AsyncMock(side_effect=[SimpleNamespace(message_thread_id=i) for i in range(10, 18)]),
            reopen_forum_topic=AsyncMock(), pin_chat_message=AsyncMock())
        self.sender = patch("app.services.media_topics_service.safe_send_once", new=AsyncMock(
            return_value=NotificationDeliveryResult(True, "sent", False, 1, message_id=90)))
        self.send = self.sender.start()

    async def asyncTearDown(self):
        self.sender.stop()
        await self.engine.dispose()

    async def setup(self):
        return await setup_media_topics(self.bot, self.settings, self.factory)

    async def test_eight_topics_navigation_pin_and_restart_reuse(self):
        first = await self.setup()
        second = await self.setup()
        self.assertEqual(first["status"], "ready")
        self.assertEqual(second["status"], "ready")
        self.assertEqual(self.bot.create_forum_topic.await_count, 8)
        self.assertEqual([c.kwargs["name"] for c in self.bot.create_forum_topic.await_args_list], list(TOPICS.values()))
        call = self.send.await_args
        self.assertEqual(call.kwargs["message_thread_id"], 10)
        self.assertIn("https://t.me/c/12345/11", call.args[3])
        self.assertEqual(call.kwargs["delivery_key"], "media-forum:-10012345:navigation:v1")
        self.bot.pin_chat_message.assert_awaited_with(-10012345, 90, disable_notification=True)
        self.assertEqual(self.bot.pin_chat_message.await_count, 1)
        self.assertEqual(self.bot.reopen_forum_topic.await_count, 8)

    async def test_reopen_explicit_rejection_retries_once_then_reuses_receipt(self):
        self.bot.reopen_forum_topic.side_effect = TelegramBadRequest(
            method=ReopenForumTopic(chat_id=-10012345, message_thread_id=10),
            message="not enough rights",
        )
        self.assertEqual((await self.setup())["status"], "needs_attention")
        self.send.assert_not_awaited()
        self.bot.reopen_forum_topic.side_effect = None
        self.assertEqual((await self.setup())["status"], "ready")
        self.assertEqual((await self.setup())["status"], "ready")
        self.assertEqual(self.bot.reopen_forum_topic.await_count, 9)
        self.assertEqual(self.bot.create_forum_topic.await_count, 8)

    async def test_reopen_network_outcome_is_not_retried(self):
        self.bot.reopen_forum_topic.side_effect = TelegramNetworkError(
            method=ReopenForumTopic(chat_id=-10012345, message_thread_id=10),
            message="timeout",
        )
        self.assertEqual((await self.setup())["status"], "needs_attention")
        self.assertEqual((await self.setup())["status"], "needs_attention")
        self.assertEqual(self.bot.reopen_forum_topic.await_count, 1)
        self.send.assert_not_awaited()
        async with self.factory() as session:
            row = await session.scalar(select(AppSetting).where(
                AppSetting.key == "media_forum:-10012345:reopen:important:10:v1"
            ))
            self.assertEqual(json.loads(row.value), {"state": "opening"})

    async def test_reopen_topic_not_modified_is_confirmed_once(self):
        self.bot.reopen_forum_topic.side_effect = TelegramBadRequest(
            method=ReopenForumTopic(chat_id=-10012345, message_thread_id=10),
            message="TOPIC_NOT_MODIFIED",
        )
        self.assertEqual((await self.setup())["status"], "ready")
        self.assertEqual((await self.setup())["status"], "ready")
        self.assertEqual(self.bot.reopen_forum_topic.await_count, 8)

    async def test_navigation_pin_explicit_rejection_can_be_retried(self):
        self.bot.pin_chat_message.side_effect = [
            TelegramBadRequest(
                method=PinChatMessage(chat_id=-10012345, message_id=90),
                message="not enough rights",
            ),
            None,
        ]
        self.assertEqual((await self.setup())["status"], "navigation_pin_unconfirmed")
        self.assertEqual((await self.setup())["status"], "ready")
        self.assertEqual((await self.setup())["status"], "ready")
        self.assertEqual(self.bot.pin_chat_message.await_count, 2)
        self.assertEqual(self.bot.create_forum_topic.await_count, 8)

    async def test_navigation_pin_ambiguous_result_is_not_retried(self):
        self.bot.pin_chat_message.side_effect = TelegramNetworkError(
            method=PinChatMessage(chat_id=-10012345, message_id=90),
            message="timeout",
        )
        self.assertEqual((await self.setup())["status"], "navigation_pin_unconfirmed")
        self.assertEqual((await self.setup())["status"], "navigation_pin_unconfirmed")
        self.assertEqual(self.bot.pin_chat_message.await_count, 1)
        async with self.factory() as session:
            row = await session.scalar(select(AppSetting).where(
                AppSetting.key == "media_forum:-10012345:navigation_pin:v1"
            ))
            self.assertEqual(json.loads(row.value), {"message_id": 90, "state": "pinning"})

    async def test_navigation_pin_conflicting_receipt_blocks_new_pin(self):
        async with self.factory() as session:
            session.add(AppSetting(
                key="media_forum:-10012345:navigation_pin:v1",
                value=json.dumps({"message_id": 91, "state": "pinned"}),
            ))
            await session.commit()
        self.assertEqual((await self.setup())["status"], "navigation_pin_unconfirmed")
        self.bot.pin_chat_message.assert_not_awaited()

    async def test_unknown_creation_is_not_repeated_and_can_be_bound(self):
        self.bot.create_forum_topic.side_effect = TelegramNetworkError(
            method=CreateForumTopic(chat_id=-10012345, name="x"), message="timeout")
        self.assertEqual((await self.setup())["status"], "needs_attention")
        await self.setup()
        self.assertEqual(self.bot.create_forum_topic.await_count, 8)
        self.send.assert_not_awaited()
        async with self.factory() as session:
            await bind_topic(session, -10012345, "tasks", 77)
            self.assertEqual(await delivery_topic(session, -10012345, "tasks"), 77)
            with self.assertRaises(ValueError):
                await bind_topic(session, -10012345, "ideas", 77)

    async def test_admin_repair_survives_rejected_inflight_creation(self):
        next_id = iter(range(10, 17))

        async def reject_after_repair(chat_id, name):
            if name == TOPICS["important"]:
                async with self.factory() as session:
                    await bind_topic(session, chat_id, "important", 99)
                raise TelegramBadRequest(
                    method=CreateForumTopic(chat_id=chat_id, name=name),
                    message="not enough rights",
                )
            return SimpleNamespace(message_thread_id=next(next_id))

        self.bot.create_forum_topic.side_effect = reject_after_repair
        self.assertEqual((await self.setup())["status"], "ready")
        async with self.factory() as session:
            self.assertEqual(await delivery_topic(session, -10012345, "important"), 99)
        await self.setup()
        self.assertEqual(self.bot.create_forum_topic.await_count, 8)

    async def test_rejected_creation_cleanup_locks_before_reading_admin_repair(self):
        # A repair committed at the cleanup lock boundary must survive the
        # failed Telegram creation; otherwise a stale "creating" row can be
        # deleted after the administrator has bound the real thread.
        from app.services.media_topics_service import _ensure_topic, _lock

        original_lock = _lock
        lock_calls = 0

        async def repair_at_cleanup_lock(session, chat_id):
            nonlocal lock_calls
            lock_calls += 1
            if lock_calls == 2:
                async with self.factory() as admin_session:
                    await bind_topic(admin_session, chat_id, "important", 99)
            await original_lock(session, chat_id)

        self.bot.create_forum_topic.side_effect = TelegramBadRequest(
            method=CreateForumTopic(chat_id=-10012345, name=TOPICS["important"]),
            message="not enough rights",
        )
        with patch("app.services.media_topics_service._lock", side_effect=repair_at_cleanup_lock):
            await _ensure_topic(self.bot, self.factory, -10012345, "important")
        self.assertEqual(lock_calls, 3)  # claim, cleanup, administrator bind
        async with self.factory() as session:
            self.assertEqual(await delivery_topic(session, -10012345, "important"), 99)
        await _ensure_topic(self.bot, self.factory, -10012345, "important")
        self.assertEqual(self.bot.create_forum_topic.await_count, 1)

    async def test_admin_repair_survives_successful_inflight_creation(self):
        next_id = iter(range(10, 18))

        async def succeed_after_repair(chat_id, name):
            thread_id = next(next_id)
            if name == TOPICS["important"]:
                async with self.factory() as session:
                    await bind_topic(session, chat_id, "important", 99)
            return SimpleNamespace(message_thread_id=thread_id)

        self.bot.create_forum_topic.side_effect = succeed_after_repair
        self.assertEqual((await self.setup())["status"], "ready")
        async with self.factory() as session:
            self.assertEqual(await delivery_topic(session, -10012345, "important"), 99)
        await self.setup()
        self.assertEqual(self.bot.create_forum_topic.await_count, 8)

    async def test_preflight_refuses_collision_plain_group_and_missing_rights(self):
        self.settings.general_chat_id = self.settings.media_chat_id
        self.assertEqual((await self.setup())["status"], "chat_not_configured")
        self.settings.general_chat_id = None
        self.bot.get_chat.return_value.is_forum = False
        self.assertEqual((await self.setup())["status"], "forum_disabled")
        self.bot.get_chat.return_value.is_forum = True
        self.bot.get_chat_member.return_value.can_pin_messages = False
        self.assertEqual((await self.setup())["status"], "missing_topic_or_pin_permissions")
        self.bot.create_forum_topic.assert_not_awaited()

    async def test_corrupt_registry_and_duplicate_ids_block_delivery(self):
        async with self.factory() as session:
            session.add(AppSetting(key="media_forum:-10012345:tasks", value="bad-json"))
            await session.commit()
            self.assertIsNone(await delivery_topic(session, -10012345, "tasks"))
            row = await session.scalar(select(AppSetting))
            row.value = json.dumps({"state": "ready", "thread_id": 42})
            session.add(AppSetting(key="media_forum:-10012345:ideas", value=row.value))
            await session.commit()
            self.assertIsNone(await delivery_topic(session, -10012345, "tasks"))

    async def test_unconfirmed_topic_with_thread_id_blocks_navigation_and_ready(self):
        # A partially recovered record may contain an ID but still have no
        # confirmed Telegram outcome. The route must remain unavailable.
        async with self.factory() as session:
            session.add(AppSetting(
                key="media_forum:-10012345:important",
                value=json.dumps({"state": "creating", "thread_id": 99}),
            ))
            await session.commit()
            self.assertIsNone(await delivery_topic(session, -10012345, "important"))
            self.assertEqual(await topic_links(session, -10012345), [])

        first = await self.setup()
        second = await self.setup()
        self.assertEqual(first["status"], "needs_attention")
        self.assertEqual(second["status"], "needs_attention")
        self.assertEqual(self.bot.create_forum_topic.await_count, 7)
        self.bot.reopen_forum_topic.assert_not_awaited()
        self.bot.pin_chat_message.assert_not_awaited()
        self.send.assert_not_awaited()

    async def test_unconfirmed_navigation_is_not_pinned(self):
        self.send.return_value = NotificationDeliveryResult(False, "uncertain", False, 1)
        self.assertEqual((await self.setup())["status"], "navigation_unconfirmed")
        self.bot.pin_chat_message.assert_not_awaited()

    async def test_miniapp_links_use_confirmed_unique_routes_only(self):
        async with self.factory() as session:
            await bind_topic(session, -10012345, "tasks", 77)
            session.add(AppSetting(key="media_forum:-10012345:ideas", value={"state": "creating"}))
            await session.commit()
            self.assertEqual(await topic_links(session, -10012345), [{
                "key": "tasks", "title": "🎯 Задания", "url": "https://t.me/c/12345/77"}])
