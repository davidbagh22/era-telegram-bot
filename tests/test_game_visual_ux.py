from app.handlers.era_game_room import _format_prompt, _learning_summary, quiz_markup
from app.services.game_content import items_for_mode
from app.services.game_formats import GameMode
from app.services.game_room_presenter import deadline, player_label


def test_answer_text_is_visible_in_card_and_buttons_stay_short():
    item = next(
        item
        for mode in GameMode
        for item in items_for_mode(mode)
        if any(len(option) > 60 for option in item.challenge.options)
    )
    room = {
        "id": "test",
        "token": "abc123",
        "mode": item.challenge.mode.value,
        "item_id": item.id,
        "expires_at": "2026-10-18T22:00:00+00:00",
        "hints_used": 0,
    }
    text, markup = _format_prompt(room)
    assert any(option in text for option in item.challenge.options if len(option) > 60)
    assert all(
        len(button.text) < 30 for row in markup.inline_keyboard for button in row
    )


def test_quiz_buttons_use_letters_instead_of_truncated_answer_copy():
    markup = quiz_markup(
        "room", ("A long answer that cannot fit in a button", "Another long answer")
    )
    assert [row[0].text for row in markup.inline_keyboard] == [
        "A · Выбрать",
        "B · Выбрать",
    ]


def test_public_card_hides_telegram_ids_and_wall_clock_deadline():
    room = {"players": {"123456789": "Участник"}}
    label = player_label(room, 123456789)
    assert "<code>" not in label and " · 123456789" not in label
    assert "Участник" in label
    assert "МСК" not in deadline({"expires_at": "2026-10-18T22:00:00+00:00"})
    assert "До " not in deadline({"expires_at": "2026-10-18T22:00:00+00:00"})


def test_quiz_result_adds_short_explanations_after_everyone_answers():
    rendered = _learning_summary({"quiz_learning": ["DNS связывает имя сайта с IP-адресом."]})
    assert "Коротко о вопросах" in rendered
    assert "DNS связывает имя сайта с IP-адресом." in rendered
