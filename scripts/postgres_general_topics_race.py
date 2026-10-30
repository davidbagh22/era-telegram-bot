"""Disposable PostgreSQL proof for durable Telegram topic claims; fake API only.

Run only in CI era_test. No real Telegram credentials, chats or messages.
"""
import asyncio
import json
import os
import uuid
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.models import AppSetting
from app.services.general_topics_service import ensure_topic


class FakeBot:
    def __init__(self, *, fail=False, hold=False):
        self.fail = fail
        self.hold = hold
        self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def get_chat(self, chat_id):
        return SimpleNamespace(is_forum=True)

    async def get_me(self):
        return SimpleNamespace(id=1)

    async def get_chat_member(self, chat_id, bot_id):
        return SimpleNamespace(status="administrator", can_manage_topics=True)

    async def create_forum_topic(self, chat_id, *, name):
        self.calls += 1
        self.entered.set()
        if self.hold:
            await self.release.wait()
        if self.fail:
            raise TimeoutError("simulated lost Telegram reply")
        return SimpleNamespace(message_thread_id=102)


async def main():
    url = os.environ["DATABASE_URL"]
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "era_test":
        raise RuntimeError("Only disposable PostgreSQL era_test is allowed")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        # A committed claim must be visible to independent PostgreSQL sessions
        # while the first simulated Telegram call is still in flight.
        chat_id = -10_000_000_000 - int(uuid.uuid4().hex[:8], 16)
        settings = Settings(
            bot_token="0000000000:CITESTTOKEN", database_url=url, general_chat_id=chat_id
        )
        bot = FakeBot(hold=True)
        first = asyncio.create_task(
            ensure_topic(bot, settings, "notifications", session_factory=sessions)
        )
        try:
            await asyncio.wait_for(bot.entered.wait(), timeout=15)
            async with sessions() as session:
                row = await session.scalar(select(AppSetting).where(
                    AppSetting.key == f"general_forum:{chat_id}:notifications"
                ))
                assert row is not None and json.loads(row.value) == {"state": "creating"}
            other = await asyncio.wait_for(asyncio.gather(*(
                ensure_topic(bot, settings, "notifications", session_factory=sessions)
                for _ in range(7)
            )), timeout=30)
            assert other == [None] * 7, other
            assert bot.calls == 1, bot.calls
        finally:
            bot.release.set()
        assert await asyncio.wait_for(first, timeout=15) == 102
        assert await ensure_topic(
            bot, settings, "notifications", session_factory=sessions
        ) == 102
        assert bot.calls == 1, bot.calls

        # An ambiguous Telegram outcome is deliberately fail-closed: no
        # second remote create even across independent PostgreSQL sessions.
        chat_id2 = chat_id - 1
        settings2 = Settings(
            bot_token="0000000000:CITESTTOKEN", database_url=url, general_chat_id=chat_id2
        )
        uncertain = FakeBot(fail=True)
        assert await ensure_topic(
            uncertain, settings2, "notifications", session_factory=sessions
        ) is None
        results = await asyncio.wait_for(asyncio.gather(*(
            ensure_topic(uncertain, settings2, "notifications", session_factory=sessions)
            for _ in range(7)
        )), timeout=30)
        assert results == [None] * 7, results
        assert uncertain.calls == 1, uncertain.calls
        async with sessions() as session:
            row = await session.scalar(select(AppSetting).where(
                AppSetting.key == f"general_forum:{chat_id2}:notifications"
            ))
            assert row is not None and json.loads(row.value) == {"state": "creating"}
        print("General topics PostgreSQL: 8 workers -> 1 fake Telegram create")
        print("General topics PostgreSQL: lost reply -> durable claim, no duplicate")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
