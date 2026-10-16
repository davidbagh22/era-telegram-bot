from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import PinChatMessage
from aiogram.types import Chat, Message, User as TelegramUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting
from app.handlers.era_game_room import _data, menu_markup
from app.services.games_launch_service import refresh_games_pin
from app.services.general_chat_menu_service import _restore_registration_pin


class GamesPinTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = SimpleNamespace(general_chat_id=-100123456, bot_username='ERA_1bot')
        self.me = TelegramUser(id=123, first_name='ERA', is_bot=True)
        self.pinned = Message(message_id=500, date=datetime.now(timezone.utc),
                              chat=Chat(id=-100123456, type='supergroup'), message_thread_id=99,
                              from_user=self.me, text='🎮 ЭРА | Интерактив\nСтарое меню')
        self.bot = SimpleNamespace(get_me=AsyncMock(return_value=self.me),
                                   get_chat=AsyncMock(return_value=SimpleNamespace(pinned_message=self.pinned)),
                                   edit_message_text=AsyncMock(return_value=True), pin_chat_message=AsyncMock(return_value=True),
                                   send_message=AsyncMock())

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_refreshes_observed_pin_without_posting_and_is_restart_safe(self):
        assert await refresh_games_pin(self.bot, self.settings, self.sessions, 99)
        assert await refresh_games_pin(self.bot, self.settings, self.sessions, 99)
        self.bot.send_message.assert_not_awaited()
        assert self.bot.edit_message_text.await_count == 2
        self.bot.pin_chat_message.assert_awaited_once_with(chat_id=-100123456, message_id=500, disable_notification=True)
        async with self.sessions() as session:
            state = _data(await session.scalar(select(AppSetting)))
        assert state['status'] == 'confirmed' and state['message_id'] == 500

    async def test_never_adopts_another_topic_or_someone_elses_pin(self):
        for thread, owner, text in ((88, self.me, '🎮 ЭРА | Интерактив'),
                                    (99, TelegramUser(id=234, first_name='Other', is_bot=False), '🎮 ЭРА | Интерактив'),
                                    (99, self.me, 'ЭРА теперь в одном боте.')):
            pinned = self.pinned.model_copy(update={'message_thread_id': thread, 'from_user': owner, 'text': text})
            self.bot.get_chat.return_value = SimpleNamespace(pinned_message=pinned)
            assert not await refresh_games_pin(self.bot, self.settings, self.sessions, 99)
        self.bot.edit_message_text.assert_not_awaited()
        self.bot.pin_chat_message.assert_not_awaited()
        self.bot.send_message.assert_not_awaited()

    async def test_permission_failures_are_bounded_and_never_repost_menu(self):
        self.bot.pin_chat_message.side_effect = TelegramForbiddenError(method=PinChatMessage(chat_id=-100123456, message_id=500), message='Forbidden')
        for _ in range(5):
            assert not await refresh_games_pin(self.bot, self.settings, self.sessions, 99)
        assert self.bot.pin_chat_message.await_count == 3
        self.bot.send_message.assert_not_awaited()
        async with self.sessions() as session:
            state = _data(await session.scalar(select(AppSetting)))
        assert state['status'] == 'needs_attention' and state['attempts'] == 3

    async def test_fallback_navigation_edition_uses_existing_ledger_once_across_restarts(self):
        from app.database.system_models import NotificationDelivery
        from app.services.games_launch_service import publish_games_launch
        self.settings.feature_games = "ALL"
        self.settings.database_url = "sqlite+aiosqlite:///:memory:"
        self.bot.get_chat.return_value = SimpleNamespace(pinned_message=self.pinned.model_copy(update={'text': 'Другой закреп'}))
        self.bot.send_message.side_effect = [self.pinned.model_copy(update={'message_id': 777}),
                                             self.pinned.model_copy(update={'message_id': 778, 'message_thread_id': 98})]
        async def topic(bot, settings, key, **kwargs):
            return 99 if key == 'games' else 98
        with patch('app.services.games_launch_service.ensure_topic', new=AsyncMock(side_effect=topic)), patch(
            'app.services.general_topics_service.ensure_topic', new=AsyncMock(side_effect=topic)
        ), patch('app.services.notification_service._session_factory', return_value=self.sessions):
            await publish_games_launch(self.bot, self.settings, self.sessions)
            await publish_games_launch(self.bot, self.settings, self.sessions)
        assert self.bot.send_message.await_count == 2  # menu edition and first announcement only
        assert self.bot.pin_chat_message.await_count == 1
        async with self.sessions() as session:
            deliveries = (await session.scalars(select(NotificationDelivery))).all()
            assert {d.delivery_key for d in deliveries} == {'general-topic:games:games-menu-identity-v2',
                                                           'general-topic:notifications:games-notification-v1'}
            assert all(d.status == 'sent' and d.attempt_count == 1 for d in deliveries)
            state = _data(await session.scalar(select(AppSetting)))
            assert state['message_id'] == 777 and state['status'] == 'confirmed'

    async def test_durable_menu_id_recovers_after_crash_before_pin_state_commit(self):
        from app.services.games_launch_service import publish_games_launch
        self.settings.feature_games = 'ALL'
        self.settings.database_url = 'sqlite+aiosqlite:///:memory:'
        self.bot.get_chat.return_value = SimpleNamespace(pinned_message=None)
        self.bot.send_message.side_effect = [self.pinned.model_copy(update={'message_id': 777}),
                                             self.pinned.model_copy(update={'message_id': 778, 'message_thread_id': 98})]
        async def topic(bot, settings, key, **kwargs):
            return 99 if key == 'games' else 98
        with patch('app.services.games_launch_service.ensure_topic', new=AsyncMock(side_effect=topic)), patch(
            'app.services.general_topics_service.ensure_topic', new=AsyncMock(side_effect=topic)
        ), patch('app.services.notification_service._session_factory', return_value=self.sessions):
            with patch('app.handlers.era_game_room._save', new=AsyncMock(side_effect=RuntimeError('simulated pin state crash'))):
                with self.assertRaises(RuntimeError):
                    await publish_games_launch(self.bot, self.settings, self.sessions)
            await publish_games_launch(self.bot, self.settings, self.sessions)
        assert self.bot.send_message.await_count == 2
        self.bot.pin_chat_message.assert_awaited_once_with(chat_id=-100123456, message_id=777, disable_notification=True)
        async with self.sessions() as session:
            state = _data(await session.scalar(select(AppSetting)))
            assert state['message_id'] == 777 and state['status'] == 'confirmed'

    async def test_deleted_confirmed_menu_gets_one_replacement_for_that_message(self):
        from aiogram.exceptions import TelegramBadRequest
        from aiogram.methods import EditMessageText
        from app.services.games_launch_service import publish_games_launch
        self.settings.feature_games = 'ALL'
        self.settings.database_url = 'sqlite+aiosqlite:///:memory:'
        assert await refresh_games_pin(self.bot, self.settings, self.sessions, 99)
        self.bot.edit_message_text.side_effect = [TelegramBadRequest(method=EditMessageText(text='x'), message='message to edit not found'), True, True]
        self.bot.send_message.side_effect = [self.pinned.model_copy(update={'message_id': 777}),
                                             self.pinned.model_copy(update={'message_id': 778, 'message_thread_id': 98})]
        async def topic(bot, settings, key, **kwargs):
            return 99 if key == 'games' else 98
        with patch('app.services.games_launch_service.ensure_topic', new=AsyncMock(side_effect=topic)), patch(
            'app.services.general_topics_service.ensure_topic', new=AsyncMock(side_effect=topic)
        ), patch('app.services.notification_service._session_factory', return_value=self.sessions):
            await publish_games_launch(self.bot, self.settings, self.sessions)
            await publish_games_launch(self.bot, self.settings, self.sessions)
        assert self.bot.send_message.await_count == 2
        assert self.bot.pin_chat_message.await_count == 2
        async with self.sessions() as session:
            state = _data(await session.scalar(select(AppSetting)))
            assert state['message_id'] == 777 and state['replacement_for'] == 500

    async def test_registration_startup_never_overwrites_game_pin(self):
        assert await _restore_registration_pin(self.bot, self.settings.general_chat_id)
        self.bot.edit_message_text.assert_not_awaited()
        self.bot.pin_chat_message.assert_not_awaited()

    async def test_registration_startup_still_refreshes_its_own_card(self):
        self.bot.get_chat.return_value = SimpleNamespace(pinned_message=self.pinned.model_copy(update={'text': 'ЭРА теперь в одном боте.\nРегистрация'}))
        assert await _restore_registration_pin(self.bot, self.settings.general_chat_id)
        self.bot.edit_message_text.assert_awaited_once()
        assert self.bot.edit_message_text.await_args.kwargs['message_id'] == 500


def test_public_menu_preserves_eleven_formats_and_opens_solo_games_privately():
    buttons = [button for row in menu_markup(public=True).inline_keyboard for button in row]
    assert len([b for b in buttons if b.url and '?start=game_' in b.url]) == 9
    assert len([b for b in buttons if b.callback_data in {'era_game:team', 'era_game:duel'}]) == 2
    assert any(b.url and b.url.endswith('?start=games') for b in buttons)
    for button in buttons:
        if button.callback_data:
            assert len(button.callback_data.encode()) <= 64
