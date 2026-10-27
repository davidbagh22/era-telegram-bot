"""Secondary plain-chat deliveries require a confirmed Tasks panel receipt."""
import json
import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.services.leaders_topics_service import delivery_topic


class PlainSecondaryReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def set_receipt(self, data):
        async with self.sessions() as session:
            session.add(AppSetting(
                key="leaders_forum:-1001:tasks", value=json.dumps(data),
            ))
            await session.commit()

    async def set_secondary(self, key="pulse"):
        async with self.sessions() as session:
            session.add(AppSetting(
                key=f"leaders_forum:-1001:{key}",
                value=json.dumps({"mode": "plain", "thread_id": None}),
            ))
            await session.commit()

    async def test_secondary_without_primary_receipt_fails_closed(self):
        for key in ("pulse", "important"):
            await self.set_secondary(key)
            async with self.sessions() as session:
                with self.assertRaisesRegex(ValueError, "Панель задач"):
                    await delivery_topic(session, -1001, key)

    async def test_uncertain_or_conflicting_primary_receipt_blocks_secondary(self):
        await self.set_secondary()
        for data in (
            {"mode": "plain", "thread_id": None, "message_state": "sending"},
            {"mode": "plain", "thread_id": None, "message_id": 91, "message_state": "uncertain"},
            {"mode": "forum", "thread_id": 91, "message_id": 92, "message_state": "sent"},
            {"mode": "plain", "thread_id": None, "message_id": True, "message_state": "sent"},
        ):
            async with self.sessions() as session:
                row = await session.get(AppSetting, "leaders_forum:-1001:tasks")
                if row is None:
                    session.add(AppSetting(key="leaders_forum:-1001:tasks", value=json.dumps(data)))
                else:
                    row.value = json.dumps(data)
                await session.commit()
            async with self.sessions() as session:
                with self.assertRaisesRegex(ValueError, "Панель задач"):
                    await delivery_topic(session, -1001, "pulse")

    async def test_confirmed_primary_allows_plain_secondary_routes(self):
        await self.set_receipt({
            "mode": "plain", "thread_id": None,
            "message_id": 91, "message_state": "sent",
        })
        await self.set_secondary("pulse")
        await self.set_secondary("important")
        async with self.sessions() as session:
            for key in ("tasks", "pulse", "important"):
                self.assertIsNone(await delivery_topic(session, -1001, key))


if __name__ == "__main__":
    unittest.main()
