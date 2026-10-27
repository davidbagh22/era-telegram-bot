"""Regression tests for fail-closed Media task card delivery."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.media_models import MediaChatNotice, MediaContentItem, MediaContentTask
from app.database.models import AppSetting, Task, User
from app.services.media_attachment_service import (
    post_missing_media_task_cards,
    task_id_for_replied_card,
)


class MediaTaskCardDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(
            bot_token="1234567890:test-token", media_chat_id=-100987654321,
        )
        async with self.factory() as session:
            session.add(AppSetting(key=f"media_forum:{self.settings.media_chat_id}:tasks",
                value=json.dumps({"thread_id": 42, "state": "ready"})))
            owner = User(telegram_id=1234, first_name="Media manager")
            session.add(owner)
            await session.flush()
            task = Task(
                title="Подготовить публикацию",
                description="Сделать макет",
                creator_id=owner.id,
                status="published",
                deadline=None,
            )
            item = MediaContentItem(
                source_kind="manual", source_key="card-test", kind="text",
                body="Сделать макет", status="assigned",
            )
            session.add_all([task, item])
            await session.flush()
            self.task_id = task.id
            session.add(MediaContentTask(
                content_id=item.id, task_id=task.id, task_kind="design",
            ))
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def notice(self):
        async with self.factory() as session:
            return await session.scalar(
                select(MediaChatNotice).where(
                    MediaChatNotice.notice_key == f"media-task-card:{self.task_id}"
                )
            )

    async def test_success_is_idempotent_and_handles_missing_deadline(self):
        bot = SimpleNamespace(send_message=AsyncMock(
            return_value=SimpleNamespace(message_id=543),
        ))
        await post_missing_media_task_cards(bot, self.settings, self.factory)
        await post_missing_media_task_cards(bot, self.settings, self.factory)
        bot.send_message.assert_awaited_once()
        self.assertIn("Без срока", bot.send_message.await_args.args[1])
        self.assertEqual((await self.notice()).telegram_message_id, 543)
        async with self.factory() as session:
            self.assertEqual(
                await task_id_for_replied_card(session, telegram_message_id=543),
                self.task_id,
            )

    async def test_ambiguous_network_error_keeps_claim_and_never_retries(self):
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=TelegramNetworkError(
            method=SendMessage(chat_id=self.settings.media_chat_id, text="test"),
            message="timeout after possible delivery",
        )))
        await post_missing_media_task_cards(bot, self.settings, self.factory)
        self.assertIsNone((await self.notice()).telegram_message_id)
        await post_missing_media_task_cards(bot, self.settings, self.factory)
        bot.send_message.assert_awaited_once()
        async with self.factory() as session:
            self.assertIsNone(
                await task_id_for_replied_card(session, telegram_message_id=543)
            )

    async def test_invalid_telegram_message_id_never_retries(self):
        for invalid_id in (None, 0, True):
            with self.subTest(invalid_id=invalid_id):
                async with self.factory() as session:
                    row = await session.scalar(select(MediaChatNotice))
                    if row is not None:
                        await session.delete(row)
                        await session.commit()
                bot = SimpleNamespace(send_message=AsyncMock(
                    return_value=SimpleNamespace(message_id=invalid_id),
                ))
                await post_missing_media_task_cards(bot, self.settings, self.factory)
                await post_missing_media_task_cards(bot, self.settings, self.factory)
                bot.send_message.assert_awaited_once()
                self.assertIsNone((await self.notice()).telegram_message_id)

    async def test_backlog_is_rate_limited_to_one_card_per_tick(self):
        async with self.factory() as session:
            owner = await session.scalar(
                select(User).where(User.telegram_id == 1234)
            )
            later_task = Task(
                title="Second queued card",
                description="Do not flood the chat",
                creator_id=owner.id,
                status="published",
                deadline=None,
            )
            item = MediaContentItem(
                source_kind="manual", source_key="second-queued-card",
                kind="text", body="Do not flood the chat", status="assigned",
            )
            session.add_all([later_task, item])
            await session.flush()
            later_id = later_task.id
            session.add(MediaContentTask(
                content_id=item.id, task_id=later_id, task_kind="design",
            ))
            await session.commit()
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=[
            SimpleNamespace(message_id=801),
            SimpleNamespace(message_id=802),
        ]))
        await post_missing_media_task_cards(bot, self.settings, self.factory)
        self.assertEqual(bot.send_message.await_count, 1)
        await post_missing_media_task_cards(bot, self.settings, self.factory)
        self.assertEqual(bot.send_message.await_count, 2)
        async with self.factory() as session:
            self.assertEqual(
                await task_id_for_replied_card(
                    session, telegram_message_id=801,
                ),
                self.task_id,
            )
            self.assertEqual(
                await task_id_for_replied_card(
                    session, telegram_message_id=802,
                ),
                later_id,
            )

    async def test_claimed_backlog_does_not_starve_newer_task_cards(self):
        # The worker's batch size is 100. Old claims must be excluded
        # *before* LIMIT or a new task can remain invisible forever.
        async with self.factory() as session:
            owner = await session.scalar(
                select(User).where(User.telegram_id == 1234)
            )
            old_tasks = [
                Task(
                    title=f"Old media task {i}",
                    description="Already claimed",
                    creator_id=owner.id,
                    status="published",
                    deadline=None,
                )
                for i in range(100)
            ]
            old_items = [
                MediaContentItem(
                    source_kind="manual",
                    source_key=f"old-card-{i}",
                    kind="text",
                    body="Already claimed",
                    status="assigned",
                )
                for i in range(100)
            ]
            session.add_all(old_tasks + old_items)
            await session.flush()
            for task, item in zip(old_tasks, old_items):
                session.add(MediaContentTask(
                    content_id=item.id, task_id=task.id, task_kind="design",
                ))
                session.add(MediaChatNotice(
                    notice_key=f"media-task-card:{task.id}",
                    notice_kind="task_card",
                    ref_type="task",
                    ref_id=task.id,
                    telegram_message_id=None,
                    sent_at=datetime.now(timezone.utc),
                ))
            session.add(MediaChatNotice(
                notice_key=f"media-task-card:{self.task_id}",
                notice_kind="task_card",
                ref_type="task",
                ref_id=self.task_id,
                telegram_message_id=543,
                sent_at=datetime.now(timezone.utc),
            ))
            await session.commit()
            newest_task = Task(
                title="Newest task must be delivered",
                description="Not yet claimed",
                creator_id=owner.id,
                status="published",
                deadline=None,
            )
            newest_item = MediaContentItem(
                source_kind="manual", source_key="newest-card",
                kind="text", body="Not yet claimed", status="assigned",
            )
            session.add_all([newest_task, newest_item])
            await session.flush()
            newest_id = newest_task.id
            session.add(MediaContentTask(
                content_id=newest_item.id, task_id=newest_id,
                task_kind="design",
            ))
            await session.commit()
        bot = SimpleNamespace(send_message=AsyncMock(
            return_value=SimpleNamespace(message_id=777),
        ))
        await post_missing_media_task_cards(bot, self.settings, self.factory)
        await post_missing_media_task_cards(bot, self.settings, self.factory)
        bot.send_message.assert_awaited_once()
        self.assertIn("Newest task must be delivered", bot.send_message.await_args.args[1])
        async with self.factory() as session:
            self.assertEqual(
                await task_id_for_replied_card(
                    session, telegram_message_id=777,
                ),
                newest_id,
            )

    async def test_preexisting_uncertain_claim_prevents_any_send(self):
        async with self.factory() as session:
            session.add(MediaChatNotice(
                notice_key=f"media-task-card:{self.task_id}",
                notice_kind="task_card", ref_type="task", ref_id=self.task_id,
                telegram_message_id=None, sent_at=datetime.now(timezone.utc),
            ))
            await session.commit()
        bot = SimpleNamespace(send_message=AsyncMock())
        await post_missing_media_task_cards(bot, self.settings, self.factory)
        bot.send_message.assert_not_awaited()


    async def test_long_description_is_truncated_without_losing_instructions(self):
        async with self.factory() as session:
            task = await session.get(Task, self.task_id)
            task.description = "Подробности " * 1000
            await session.commit()
        bot = SimpleNamespace(send_message=AsyncMock(
            return_value=SimpleNamespace(message_id=910),
        ))
        await post_missing_media_task_cards(bot, self.settings, self.factory)
        bot.send_message.assert_awaited_once()
        text = bot.send_message.await_args.args[1]
        self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 4096)
        self.assertIn("текст сокращён", text)
        self.assertIn("Без срока", text)
        self.assertIn("ответьте именно на эту карточку", text)
        self.assertEqual((await self.notice()).telegram_message_id, 910)

    async def test_emoji_heavy_task_does_not_exceed_telegram_utf16_limit(self):
        async with self.factory() as session:
            task = await session.get(Task, self.task_id)
            task.title = "🎬" * 3000
            task.description = "📸" * 3000
            await session.commit()
        bot = SimpleNamespace(send_message=AsyncMock(
            return_value=SimpleNamespace(message_id=911),
        ))
        await post_missing_media_task_cards(bot, self.settings, self.factory)
        bot.send_message.assert_awaited_once()
        text = bot.send_message.await_args.args[1]
        self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 4096)
        self.assertIn("текст сокращён", text)
        self.assertIn("Баллы после проверки", text)
        self.assertEqual((await self.notice()).telegram_message_id, 911)


if __name__ == "__main__":
    unittest.main()
