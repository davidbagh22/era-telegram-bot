from app.handlers.era_spyfall import LOCATIONS, MIN_PLAYERS, _card


def test_spyfall_lobby_shows_ready_state_and_private_role_link():
    room = {
        "status": "lobby",
        "token": "abc123",
        "bot_username": "ERA_1bot",
        "participants": [1, 2, 3, 4],
        "players": {str(i): f"Игрок {i}" for i in range(1, 5)},
        "private_ready": ["1", "2", "3", "4"],
        "creator_id": 1,
        "active_user": 1,
    }
    text, markup = _card(room)
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert "4/4" in text and all(name in text for name in room["players"].values())
    assert any(
        button.url == "https://t.me/ERA_1bot?start=spy_abc123" for button in buttons
    )
    assert any(button.callback_data == "spy:start:abc123" for button in buttons)
    assert MIN_PLAYERS == 4


def test_spyfall_locations_are_unique_and_neutral():
    assert len(LOCATIONS) == len(set(LOCATIONS))
    assert len(LOCATIONS) >= 15
    assert not any(
        "полит" in location.casefold() or "войн" in location.casefold()
        for location in LOCATIONS
    )


def test_vote_keyboard_uses_short_callback_data():
    room = {
        "status": "voting",
        "token": "abc123",
        "participants": [1, 2, 3, 4],
        "players": {str(i): f"Имя игрока {i}" for i in range(1, 5)},
        "votes": {},
    }
    _, markup = _card(room)
    callbacks = [
        button.callback_data for row in markup.inline_keyboard for button in row
    ]
    assert all(len(value.encode()) <= 64 for value in callbacks)
