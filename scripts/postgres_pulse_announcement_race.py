"""Exercise Pulse announcement claims on disposable CI PostgreSQL only."""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.models import AppSetting
from app.database.system_models import NotificationDelivery
from app.services.leadership_weekly_service import _send_cycle_announcement


class FakeBot:
    def __init__(self):
        self.calls = []

    async def get_me(self):
        return SimpleNamespace(username="era_ci_bot")

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append((chat_id, kwargs.get("message_thread_id")))
        await asyncio.sleep(0)
        return SimpleNamespace(message_id=121)


async def main():
    url = os.environ["DATABASE_URL"]
    parsed = make_url(url)
    if parsed.database != "era_test" or parsed.get_backend_name() != "postgresql":
        raise RuntimeError("Only isolated PostgreSQL era_test is allowed")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    cycle_id = int(uuid.uuid4().hex[:7], 16)
    chat_id = -10_000_000_000 - cycle_id
    settings = Settings(bot_token="0000000000:CITESTTOKEN", database_url=url, leaders_chat_id=chat_id)
    bot = FakeBot()
    deadline = datetime.now(timezone.utc)
    try:
        async with factory() as session:
            session.add(AppSetting(key=f"leaders_forum:{chat_id}:pulse", value=json.dumps({"mode": "forum", "thread_id": 7})))
            await session.commit()

        async def send(submitted=0):
            async with factory() as session:
                cycle = SimpleNamespace(id=cycle_id, week_number=43, submitted_count=submitted,
                    eligible_count=8, announcement_message_id=None)
                sent = await _send_cycle_announcement(session, bot, settings, cycle, deadline)
                await session.commit()
                return sent
        results = await asyncio.wait_for(asyncio.gather(*(send() for _ in range(8))), 45)
        assert any(results), results
        assert bot.calls == [(chat_id, 7)], bot.calls
        assert await send(submitted=3)
        assert len(bot.calls) == 1
        async with factory() as session:
            receipt = await session.scalar(select(NotificationDelivery).where(
                NotificationDelivery.delivery_key == f"leadership-pulse-announcement:{cycle_id}"))
            assert receipt.status == "sent" and receipt.message_id == 121
        print("Pulse PostgreSQL: 8 workers -> 1 send; changed-counter replay restores receipt without a duplicate")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
