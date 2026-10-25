from app.services import community_welcome_service as welcome


def test_general_chat_has_exactly_1000_base_combinations() -> None:
    assert welcome.combination_count() == 1000


def test_general_chat_welcomes_do_not_repeat_for_full_cycle() -> None:
    welcome._queue.clear()
    messages = [welcome.build_general_chat_welcome(["Алекс"]) for _ in range(1000)]

    assert len(messages) == 1000
    assert len(set(messages)) == 1000
    assert all("@ERA_1bot" in message for message in messages)
    assert all("Алекс" in message for message in messages)
    assert all("ЭРА" in message for message in messages)


def test_general_chat_welcome_highlights_community_and_bot_capabilities() -> None:
    welcome._queue.clear()
    text = welcome.build_general_chat_welcome(["Мария"])

    assert "сообществ" in text.lower()
    assert "@ERA_1bot" in text
    assert any(word in text.lower() for word in ("мероприят", "портфолио", "балл", "возможност"))
