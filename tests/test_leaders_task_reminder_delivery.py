import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting, Task, TaskDelivery, User
from app.services.notification_service import _session_factory
from app.services.scheduler_service import _send_leaders_task_reminder, send_task_reminders


class LeadersTaskReminderDeliveryTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        url = f"sqlite+aiosqlite:///{Path(self.tmp.name) / 'reminder.db'}"
        self.settings = Settings(bot_token="0000000000:CITESTTOKEN", database_url=url, timezone="UTC", leaders_chat_id=-1001)
        self.engine = create_async_engine(url)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=42)))
        self.delivery = SimpleNamespace(id=1, chat_id=-1001, message_thread_id=7)

    async def asyncTearDown(self):
        await self.engine.dispose()
        _session_factory.cache_clear()
        self.tmp.cleanup()

    async def configure(self, session, data):
        session.add(AppSetting(key="leaders_forum:-1001:tasks", value=json.dumps(data)))
        await session.commit()

    async def send(self, session):
        return await _send_leaders_task_reminder(session, self.bot, self.settings, self.delivery, stage=1, text="Срок задачи")

    async def test_replay_after_lost_business_ack_sends_only_once(self):
        async with self.factory() as session:
            await self.configure(session, {"mode": "forum", "thread_id": 7})
            self.assertTrue(await self.send(session))
            self.assertTrue(await self.send(session))
            self.bot.send_message.assert_awaited_once()
            self.assertEqual(self.bot.send_message.await_args.kwargs["message_thread_id"], 7)

    async def test_uncertain_delivery_never_resends(self):
        self.bot.send_message.side_effect = TelegramNetworkError(method=SendMessage(chat_id=-1001, text="test"), message="timeout")
        async with self.factory() as session:
            await self.configure(session, {"mode": "forum", "thread_id": 7})
            self.assertFalse(await self.send(session))
            self.assertFalse(await self.send(session))
            self.bot.send_message.assert_awaited_once()

    async def test_unknown_or_creating_topic_blocks_stale_card(self):
        for data in ({"mode": "broken", "thread_id": 7}, {"mode": "forum", "thread_id": 7, "thread_state": "creating"}):
            async with self.factory() as session:
                session.add(AppSetting(key="leaders_forum:-1001:tasks", value=json.dumps(data)))
                await session.flush()
                self.assertFalse(await self.send(session))
                await session.rollback()
        self.bot.send_message.assert_not_awaited()

    async def test_changed_chat_or_topic_does_not_retarget_old_card(self):
        async with self.factory() as session:
            await self.configure(session, {"mode": "forum", "thread_id": 8})
            self.assertFalse(await self.send(session))
            self.settings.leaders_chat_id = -1002
            self.assertFalse(await self.send(session))
            self.settings.leaders_chat_id = self.settings.general_chat_id = -1001
            self.assertFalse(await self.send(session))
            self.bot.send_message.assert_not_awaited()

    async def test_explicit_plain_mode_is_supported(self):
        async with self.factory() as session:
            await self.configure(session, {"mode": "plain", "thread_id": None})
            self.delivery.message_thread_id = None
            self.assertTrue(await self.send(session))
            self.assertNotIn("message_thread_id", self.bot.send_message.await_args.kwargs)

    async def test_scheduler_preserves_stage_on_failure_and_resumes_without_duplicate(self):
        async with self.factory() as session:
            await self.configure(session, {"mode": "forum", "thread_id": 7})
            owner = User(telegram_id=999, first_name="Creator", is_blocked=True)
            session.add(owner)
            await session.flush()
            now = datetime.now(timezone.utc)
            task = Task(title="Due task", description="test", creator_id=owner.id,
                        status="in_progress", deadline=now + timedelta(hours=2),
                        remind_at=now - timedelta(minutes=1))
            session.add(task)
            await session.flush()
            delivery = TaskDelivery(task_id=task.id, chat_key="leaders", chat_id=-1001,
                                    message_thread_id=7, status="sent", telegram_message_id=41,
                                    remind_at=now - timedelta(minutes=1))
            session.add(delivery)
            await session.commit()
            task_id, delivery_id = task.id, delivery.id
        self.bot.send_message.side_effect = TelegramNetworkError(method=SendMessage(chat_id=-1001, text="test"), message="timeout")
        await send_task_reminders(self.bot, self.settings, self.factory)
        await send_task_reminders(self.bot, self.settings, self.factory)
        self.bot.send_message.assert_awaited_once()
        async with self.factory() as session:
            self.assertEqual((await session.get(Task, task_id)).reminder_count, 0)
            self.assertEqual((await session.get(TaskDelivery, delivery_id)).reminder_count, 0)

    async def test_revoked_media_membership_blocks_private_reminder_to_old_assignee(self):
        async with self.factory() as session:
            owner = User(telegram_id=998, first_name="Former leader", application_status="approved")
            member = User(telegram_id=999, first_name="Former member", application_status="approved")
            session.add_all([owner, member])
            await session.flush()
            now = datetime.now(timezone.utc)
            session.add(Task(title="Private media task", description="Restricted", creator_id=owner.id,
                             assignee_id=member.id, status="in_progress", reward_json={"media_task": True},
                             deadline=now + timedelta(hours=2), remind_at=now - timedelta(minutes=1)))
            await session.commit()
        await send_task_reminders(self.bot, self.settings, self.factory)
        self.bot.send_message.assert_not_awaited()
