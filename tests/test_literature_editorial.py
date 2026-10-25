import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import AppSetting, User
from app.database.system_models import NotificationDelivery
from app.services.book_club_service import (approve_editorial_item, editorial_revision, editorial_settings,
    parse_editorial_text, publish_editorial_item, render_editorial, run_editorial_queue, save_editorial_item, save_editorial_settings)
from app.utils.constants import ApplicationStatus, Role

MATERIAL = ('Название: Читаем вместе\nАвтор: Редакция ЭРА\nВведение: Разговор о памяти.\n'
            'Главная мысль: У каждого есть история, которую хочется сохранить.\n'
            'Вопрос: Какую книгу Вы бы передали другу?\nИсточник: Материал редактора')


class EditorialTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='1234567890:test', general_chat_id=-1001)
        self.now = datetime(2026, 10, 17, 16, tzinfo=timezone.utc)
        self.bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=7)),
                                   create_forum_topic=AsyncMock())
        self.patches = [patch(module+'._session_factory', return_value=self.sessions) for module in (
            'app.services.notification_service', 'app.services.general_topics_service')]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        async with self.sessions() as session:
            editor = User(telegram_id=11, first_name='Editor', role=Role.ADMIN, application_status=ApplicationStatus.APPROVED)
            subscriber = User(telegram_id=22, first_name='Reader', book_club_subscribed=True,
                              application_status=ApplicationStatus.APPROVED)
            unsubscribed = User(telegram_id=33, first_name='No subscription', application_status=ApplicationStatus.APPROVED)
            session.add_all([editor, subscriber, unsubscribed])
            await session.flush()
            self.editor_id = editor.id
            session.add(AppSetting(key='general_forum:-1001:literature', value=json.dumps({'thread_id': 26216})))
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def draft(self, *, approve=False):
        async with self.sessions() as session:
            item = await save_editorial_item(session, MATERIAL, actor_id=self.editor_id)
            if approve:
                await approve_editorial_item(session, item.id, editorial_revision(item), actor_id=self.editor_id)
            await session.commit()
            return item

    async def enable(self, **changes):
        async with self.sessions() as session:
            await save_editorial_settings(session, actor_id=self.editor_id, enabled=True, **changes)
            await session.commit()

    async def test_only_reviewed_material_is_scheduled_and_a_restart_does_not_repeat_it(self):
        draft = await self.draft()
        await self.enable()
        await run_editorial_queue(self.bot, self.settings, self.sessions, now=self.now)
        self.bot.send_message.assert_not_awaited()
        async with self.sessions() as session:
            await approve_editorial_item(session, draft.id, editorial_revision(draft), actor_id=self.editor_id)
            await session.commit()
        await run_editorial_queue(self.bot, self.settings, self.sessions, now=self.now)
        await run_editorial_queue(self.bot, self.settings, self.sessions, now=self.now)
        assert self.bot.send_message.await_count == 2
        recipients = {c.args[0] for c in self.bot.send_message.await_args_list}
        assert recipients == {-1001, 22}
        public = next(c for c in self.bot.send_message.await_args_list if c.args[0] < 0)
        assert public.kwargs['message_thread_id'] == 26216
        self.bot.create_forum_topic.assert_not_awaited()
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(NotificationDelivery)) == 2

    async def test_pause_schedule_and_next_material_are_controlled(self):
        await self.draft(approve=True)
        await self.draft(approve=True)
        await self.enable(paused=True)
        await run_editorial_queue(self.bot, self.settings, self.sessions, now=self.now)
        self.bot.send_message.assert_not_awaited()
        await self.enable(paused=False, hour=20, minute=0)
        await run_editorial_queue(self.bot, self.settings, self.sessions, now=self.now)  # 19:00 MSK
        self.bot.send_message.assert_not_awaited()
        await run_editorial_queue(self.bot, self.settings, self.sessions, now=self.now+timedelta(hours=1))
        await run_editorial_queue(self.bot, self.settings, self.sessions, now=self.now+timedelta(days=1, hours=1))
        assert self.bot.send_message.await_count == 4

    async def test_editing_revokes_approval_and_old_preview_cannot_approve_new_text(self):
        item = await self.draft(approve=True)
        revision = editorial_revision(item)
        async with self.sessions() as session:
            updated = await save_editorial_item(session, MATERIAL.replace('Читаем вместе', 'Книга месяца'),
                                                actor_id=self.editor_id, item_id=item.id)
            assert not updated.is_enabled
            with self.assertRaises(ValueError):
                await approve_editorial_item(session, item.id, revision, actor_id=self.editor_id)
            await session.commit()

    async def test_manual_publication_uses_the_same_once_key_and_requires_review(self):
        item = await self.draft()
        async with self.sessions() as session:
            with self.assertRaises(ValueError):
                await publish_editorial_item(self.bot, self.settings, session, item.id, editorial_revision(item))
            await approve_editorial_item(session, item.id, editorial_revision(item), actor_id=self.editor_id)
            await session.commit()
            assert await publish_editorial_item(self.bot, self.settings, session, item.id, editorial_revision(item)) == 'sent'
            await session.commit()
        async with self.sessions() as session:
            assert await publish_editorial_item(self.bot, self.settings, session, item.id, editorial_revision(item)) == 'already_sent'
        assert self.bot.send_message.await_count == 2

    async def test_unknown_outcome_pauses_queue_instead_of_sending_again(self):
        await self.draft(approve=True)
        await self.enable()
        self.bot.send_message.side_effect = TelegramNetworkError(method=SendMessage(chat_id=-1001, text='test'), message='unknown')
        await run_editorial_queue(self.bot, self.settings, self.sessions, now=self.now)
        await run_editorial_queue(self.bot, self.settings, self.sessions, now=self.now)
        assert self.bot.send_message.await_count == 1
        async with self.sessions() as session:
            assert (await editorial_settings(session))['paused']


def test_editorial_structure_and_html_escaping_are_verified_before_save():
    assert '&lt;память&gt;' in render_editorial(parse_editorial_text(MATERIAL.replace('памяти', '<память>')))
    for invalid in ('Нет обязательных полей', MATERIAL.replace('Вопрос:', 'Ответ:')):
        try:
            parse_editorial_text(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('Unstructured content must remain outside the publication queue')
