from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.media_models import MediaContentItem
from app.services.media_service import publish_content


class FakeChannelBot:
    def __init__(self) -> None:
        self.messages: list[tuple[object, str]] = []
        self.polls: list[tuple[object, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))
        return SimpleNamespace(message_id=9000 + len(self.messages))

    async def send_poll(self, chat_id, question, options, **kwargs):
        self.polls.append((chat_id, question))
        return SimpleNamespace(message_id=9100 + len(self.polls))


class MediaAutoSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(
            bot_token="1234567890:test-token",
            era_channel_id="-1001234567890",
        )

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_dynamic_event_or_project_request_can_never_auto_publish(self) -> None:
        bot = FakeChannelBot()
        async with self.factory() as session:
            item = MediaContentItem(
                source_kind="request",
                source_key="event:55:announcement",
                source_type="event",
                source_id=55,
                kind="text",
                body="Dynamic event content with names/numbers",
                scheduled_at=datetime.now(timezone.utc),
                status="scheduled",
            )
            session.add(item)
            await session.commit()
            result = await publish_content(session, bot, self.settings, item, manual=False)

        self.assertFalse(result.ok)
        self.assertEqual(result.code, "auto_authored_only")
        self.assertEqual(bot.messages, [])
        self.assertEqual(bot.polls, [])

    async def test_authored_scheduled_content_is_published_exactly_once(self) -> None:
        bot = FakeChannelBot()
        async with self.factory() as session:
            item = MediaContentItem(
                source_kind="authored_pack",
                source_key="pack:test:1",
                kind="text",
                body="Заранее утверждённый evergreen материал",
                scheduled_at=datetime.now(timezone.utc),
                status="scheduled",
            )
            session.add(item)
            await session.commit()
            first = await publish_content(session, bot, self.settings, item, manual=False)
            second = await publish_content(session, bot, self.settings, item, manual=False)

        self.assertTrue(first.ok)
        self.assertEqual(first.code, "published")
        self.assertFalse(second.ok)
        self.assertEqual(second.code, "already_published")
        self.assertEqual(len(bot.messages), 1)

    async def test_authored_poll_uses_poll_channel_api_once(self) -> None:
        bot = FakeChannelBot()
        async with self.factory() as session:
            item = MediaContentItem(
                source_kind="authored_pack",
                source_key="pack:test:poll",
                kind="poll",
                poll_question="Что выбираем?",
                poll_options=["Первое", "Второе"],
                scheduled_at=datetime.now(timezone.utc),
                status="scheduled",
            )
            session.add(item)
            await session.commit()
            result = await publish_content(session, bot, self.settings, item, manual=False)

        self.assertTrue(result.ok)
        self.assertEqual(len(bot.polls), 1)
        self.assertEqual(bot.messages, [])


if __name__ == "__main__":
    unittest.main()
