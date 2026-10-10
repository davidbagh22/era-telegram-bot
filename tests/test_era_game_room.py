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


def test_room_bound_to_chat_and_thread():
    assert _key(-1001, 10, "team") != _key(-1001, 11, "team")
    assert _key(-1001, 10, "team") != _key(-1002, 10, "team")


def test_game_menu_callbacks_are_short_and_in_namespace():
    for row in menu_markup().inline_keyboard:
        for button in row:
            assert button.callback_data.startswith("era_game:")
            assert len(button.callback_data.encode()) <= 64
    for row in lobby_markup("team").inline_keyboard:
        for button in row:
            assert len(button.callback_data.encode()) <= 64
    for row in quiz_markup("team", ("One", "Two", "Three")).inline_keyboard:
        for button in row:
            assert len(button.callback_data.encode()) <= 64


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
    assert not any("Игровая" in label for label in labels)
    bot.create_forum_topic.assert_not_awaited()
