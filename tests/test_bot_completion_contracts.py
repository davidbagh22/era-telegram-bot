import pytest

from app.handlers.participant.development import (
    _goal_review_keyboard,
    _question_keyboard,
    _vector_home_keyboard,
)
from app.keyboards.bot_shell import (
    contact_keyboard,
    main_inline_keyboard,
    navigation_guide_keyboard,
)
from app.services.bot_notification_service import PrimaryAction, action_markup


def _labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_primary_notification_action_requires_exactly_one_target() -> None:
    with pytest.raises(ValueError):
        PrimaryAction(label="Открыть")
    with pytest.raises(ValueError):
        PrimaryAction(
            label="Открыть",
            callback_data="one",
            web_app_url="https://example.com/app",
        )


def test_primary_notification_markup_has_one_clear_action() -> None:
    markup = action_markup(PrimaryAction(label="Продолжить", callback_data="vector:start"))

    assert len(markup.inline_keyboard) == 1
    assert len(markup.inline_keyboard[0]) == 1
    assert markup.inline_keyboard[0][0].text == "Продолжить"
    assert markup.inline_keyboard[0][0].callback_data == "vector:start"


def test_participant_bot_shell_keeps_app_primary_and_vector_native() -> None:
    labels = _labels(main_inline_keyboard(miniapp_url="https://example.com/app"))

    assert labels[0] == "🔥 Открыть ЭРА"
    assert "🧭 Мой вектор" in labels
    assert "🧭 Навигация" in labels
    assert "💬 Связь" in labels
    assert "👤 Личный кабинет" not in labels


def test_role_shell_adds_only_relevant_workspace() -> None:
    leader = _labels(
        main_inline_keyboard(
            privileged=True,
            miniapp_url="https://example.com/app",
        )
    )
    admin = _labels(
        main_inline_keyboard(
            privileged=True,
            admin=True,
            miniapp_url="https://example.com/app",
        )
    )

    assert "🧭 Режим лидера" in leader
    assert "⚙️ Управление ЭРА" not in leader
    assert "⚙️ Управление ЭРА" in admin
    assert "🧭 Режим лидера" not in admin


def test_navigation_exposes_qr_only_to_operational_roles() -> None:
    participant = _labels(navigation_guide_keyboard("https://example.com/app"))
    leader = _labels(
        navigation_guide_keyboard(
            "https://example.com/app",
            privileged=True,
        )
    )

    assert "🧭 Мой вектор" in participant
    assert "🎟 QR вход на событие" not in participant
    assert "🎟 QR вход на событие" in leader


def test_contact_is_a_compact_service_centre() -> None:
    labels = _labels(contact_keyboard())

    assert labels == [
        "❓ Задать вопрос",
        "👥 Кто за что отвечает",
        "🏛 Департаменты",
        "💬 Чаты",
        "📜 Правила",
        "ℹ️ О боте",
        "← Главное меню",
    ]


def test_my_vector_home_resumes_existing_checkin() -> None:
    labels = _labels(
        _vector_home_keyboard(
            completed=False,
            started=True,
            miniapp_url="https://example.com/app",
        )
    )

    assert labels[0] == "Продолжить Check-in"
    assert "⚡ Быстрый пульс" in labels
    assert "Моя карта года" in labels


def test_my_vector_questions_and_goal_review_are_button_driven() -> None:
    question = _question_keyboard("energy")
    goal = _goal_review_keyboard(12)

    # Five explicit response choices (0..4) plus the non-destructive exit row.
    assert len(question.inline_keyboard) == 6
    answer_buttons = [row[0] for row in question.inline_keyboard[:-1]]
    assert [button.text.split(" · ", 1)[0] for button in answer_buttons] == [
        "0",
        "1",
        "2",
        "3",
        "4",
    ]
    assert all(
        button.callback_data.startswith("vector:answer:energy:")
        for button in answer_buttons
    )
    assert question.inline_keyboard[-1][0].text == "Сохранить и выйти"
    assert _labels(goal) == [
        "Сделал",
        "Частично",
        "Не получилось",
        "Передумал",
        "Цель потеряла смысл",
    ]