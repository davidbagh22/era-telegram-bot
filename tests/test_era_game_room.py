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
