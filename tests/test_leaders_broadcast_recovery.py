from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.leadership_models import BroadcastAcknowledgement
from app.database.models import Broadcast, User
from app.handlers.leaders_broadcast import announcement_action


class LeadersBroadcastRecoveryTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = SimpleNamespace(leaders_chat_id=-100456, admin_ids=[1])
        self.bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=707)), edit_message_text=AsyncMock())
        self.state = SimpleNamespace(clear=AsyncMock())
        async with self.sessions() as session:
            self.user = User(telegram_id=1, first_name="Admin", phone="+10000001", role="admin")
            session.add(self.user)
            await session.flush()
            self.broadcast = Broadcast(title="Важное", text="Текст команды", audience_type="leaders", author_id=self.user.id, status="draft",
                audience_filter_json={"kind": "important", "recipients": [self.user.id], "chat_id": -100456})
            session.add(self.broadcast)
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    def call(self, action):
        return SimpleNamespace(data=f"leaders_broadcast:{action}:{self.broadcast.id}", answer=AsyncMock(),
            message=SimpleNamespace(message_id=707, chat=SimpleNamespace(id=-100456), answer=AsyncMock()))

    async def test_dispatch_persists_message_id_in_json_after_commit(self):
        with patch("app.handlers.leaders_broadcast.verify_member", new=AsyncMock(return_value=True)), \
             patch("app.handlers.leaders_broadcast.roster", new=AsyncMock(return_value=[self.user])), \
             patch("app.handlers.leaders_broadcast.topic_id", new=AsyncMock(return_value=99)), \
             patch("app.handlers.leaders_broadcast.audit", new=AsyncMock()):
            async with self.sessions() as session:
                await announcement_action(self.call("important"), self.state, self.user, self.settings, session, self.bot)
                await session.commit()
        async with self.sessions() as session:
            broadcast = await session.get(Broadcast, self.broadcast.id)
            self.assertEqual(broadcast.status, "sent")
            self.assertEqual(broadcast.audience_filter_json["message_id"], 707)

    async def test_legacy_read_repairs_missing_message_id_and_is_idempotent(self):
        async with self.sessions() as session:
            broadcast = await session.get(Broadcast, self.broadcast.id)
            broadcast.status = "sent"
            await session.commit()
        with patch("app.handlers.leaders_broadcast.verify_member", new=AsyncMock(return_value=True)):
            for _ in range(2):
                async with self.sessions() as session:
                    await announcement_action(self.call("read"), self.state, self.user, self.settings, session, self.bot)
                    await session.commit()
        async with self.sessions() as session:
            broadcast = await session.get(Broadcast, self.broadcast.id)
            count = await session.scalar(select(func.count()).select_from(BroadcastAcknowledgement))
            self.assertEqual(broadcast.audience_filter_json["message_id"], 707)
            self.assertEqual(count, 1)
        self.bot.send_message.assert_not_awaited()
        self.assertEqual(self.bot.edit_message_text.await_args.kwargs["message_id"], 707)

    async def test_malformed_callback_is_ignored_without_a_database_query(self):
        call = self.call("read")
        call.data = "leaders_broadcast:read:broken"
        session = SimpleNamespace(scalar=AsyncMock())
        await announcement_action(call, self.state, self.user, self.settings, session, self.bot)
        session.scalar.assert_not_awaited()
