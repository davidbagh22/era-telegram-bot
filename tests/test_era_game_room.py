"""Safety and routing regression tests for the guarded Telegram game-room pilot."""
from app.handlers.era_game_room import (
    MAX_PLAYERS, MIN_PLAYERS, QUESTIONS, WAIT_SECONDS,
    _enabled, _key, lobby_markup, menu_markup, quiz_markup,
)


class SettingsStub:
    feature_games = "OFF"
    feature_tester_ids = [11]


def test_games_disabled_by_default():
    settings = SettingsStub()
    assert not _enabled(settings, 11)
    assert not _enabled(settings, 99)
    settings.feature_games = "TESTERS"
    assert _enabled(settings, 11)
    assert not _enabled(settings, 99)
    settings.feature_games = "ALL"
    assert _enabled(settings, 11)
    assert _enabled(settings, 99)


def test_room_bound_to_chat_and_thread():
    assert _key(-1001, 10, "team") != _key(-1001, 11, "team")
    assert _key(-1001, 10, "team") != _key(-1002, 10, "team")


def test_game_menu_callbacks_are_short_and_in_namespace():
    for public in (False, True):
        callbacks = [button.callback_data for row in menu_markup(public=public).inline_keyboard
                     for button in row if button.callback_data]
        assert callbacks.count('leisure:home') == (0 if public else 1)
        for callback in callbacks:
            assert callback.startswith(("era_game:", "era_spyfall:")) or not public and callback == 'leisure:home'
            assert len(callback.encode()) <= 64
    for row in lobby_markup("team").inline_keyboard:
        for button in row:
            assert len(button.callback_data.encode()) <= 64
    for row in quiz_markup("team", ("One", "Two", "Three")).inline_keyboard:
        for button in row:
            assert len(button.callback_data.encode()) <= 64


def test_menu_exposes_all_eleven_distinct_playable_modes():
    from app.services.game_formats import GameMode
    from app.handlers.era_game_room import menu_markup

    callbacks = [button.callback_data for row in menu_markup().inline_keyboard for button in row]
    game_callbacks = [callback for callback in callbacks if callback in {
        "era_game:solo", "era_game:team", "era_game:duel"
    } or callback.startswith("era_game:play:")]
    modes = {callback.rsplit(":", 1)[-1] for callback in game_callbacks}
    assert len(game_callbacks) == len(GameMode)
    assert modes == {"solo", "team", "duel", *{mode.value for mode in GameMode if mode not in {
        GameMode.SOLO_QUIZ, GameMode.TEAM_QUIZ, GameMode.TEAM_DUEL
    }}}


def test_room_limits_and_question_bank():
    assert MIN_PLAYERS == 2
    assert MAX_PLAYERS >= MIN_PLAYERS
    assert WAIT_SECONDS >= 60
    assert len(QUESTIONS) == len(set(question for question, _, _ in QUESTIONS))
    for question, choices, correct in QUESTIONS:
        assert question and len(choices) >= 2
        assert 0 <= correct < len(choices)


def test_leisure_is_accessible_from_both_bot_keyboards():
    from app.keyboards.bot_shell import main_inline_keyboard, main_reply_keyboard
    reply_labels = [button.text for row in main_reply_keyboard().keyboard for button in row]
    assert "🎲 Досуг" in reply_labels
    assert "📚 Литература" not in reply_labels
    inline_buttons = [button for row in main_inline_keyboard().inline_keyboard for button in row]
    assert any(button.callback_data == "leisure:home" for button in inline_buttons)


def test_leisure_hides_game_link_until_public_launch():
    import asyncio
    from unittest.mock import AsyncMock, Mock
    from app.handlers.era_leisure import _markup

    settings = SettingsStub()
    settings.general_chat_id = -1001234567890
    bot = Mock()
    bot.create_forum_topic = AsyncMock()
    keyboard = asyncio.run(_markup(bot, settings))
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert any("Литература" in label for label in labels)
    assert not any("Интерактив" in label for label in labels)
    bot.create_forum_topic.assert_not_awaited()


def test_general_chat_topic_routing_preserves_existing_topic_keys():
    from app.services.general_topics_service import TOPICS, SETUP_TOPICS
    assert TOPICS["announcements"] == "Мероприятия"
    assert TOPICS["notifications"] == "Оповещения"
    assert TOPICS["games"] == "🎮 Интерактив"
    assert "announcements" in SETUP_TOPICS
    assert "notifications" in SETUP_TOPICS


def test_testers_can_navigate_without_public_launch():
    import asyncio
    from unittest.mock import AsyncMock, Mock, patch
    from app.handlers.era_leisure import _markup
    settings = SettingsStub()
    settings.feature_games = 'TESTERS'
    settings.general_chat_id = -1001234567890
    with patch('app.handlers.era_leisure.ensure_topic', new=AsyncMock(return_value=10)):
        tester = asyncio.run(_markup(Mock(), settings, 11))
        public = asyncio.run(_markup(Mock(), settings, 22))
    assert any('Интерактив' in b.text for row in tester.inline_keyboard for b in row)
    assert not any('Интерактив' in b.text for row in public.inline_keyboard for b in row)


def test_no_public_launch_during_off_or_testers():
    import asyncio
    from unittest.mock import AsyncMock, Mock, patch
    from app.services.games_launch_service import publish_games_launch
    settings = SettingsStub()
    settings.general_chat_id = -1001234567890
    with patch('app.services.games_launch_service.ensure_topic', new=AsyncMock()) as topic:
        for mode in ('OFF', 'TESTERS'):
            settings.feature_games = mode
            asyncio.run(publish_games_launch(Mock(), settings, Mock()))
        topic.assert_not_awaited()


def test_group_commands_accept_bot_mention():
    import asyncio
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from aiogram.types import Chat, Message
    from app.handlers.era_game_room import router
    command_filter = router.message.handlers[0].filters[0].callback
    bot = SimpleNamespace(me=AsyncMock(return_value=SimpleNamespace(username='ERA_1bot')))
    for text in ('/games', '/game@ERA_1bot', '/games@ERA_1bot'):
        message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=-100123, type='supergroup'), text=text)
        assert asyncio.run(command_filter(message, bot))
    other = Message(message_id=2, date=datetime.now(timezone.utc), chat=Chat(id=-100123, type='supergroup'), text='/games@other_bot')
    assert not asyncio.run(command_filter(other, bot))
