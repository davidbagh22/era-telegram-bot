from aiogram.types import ReplyKeyboardMarkup

from app.keyboards.faq import (
    GENERAL_CHAT_EVENTS_TEXT,
    GENERAL_CHAT_PROFILE_TEXT,
    general_chat_navigation_keyboard,
)
from app.utils.deep_links import (
    telegram_event_miniapp_url,
    telegram_profile_miniapp_url,
)


def test_general_chat_navigation_is_persistent_two_action_dock() -> None:
    keyboard = general_chat_navigation_keyboard()

    assert isinstance(keyboard, ReplyKeyboardMarkup)
    assert keyboard.is_persistent is True
    assert len(keyboard.keyboard) == 1
    assert [button.text for button in keyboard.keyboard[0]] == [
        GENERAL_CHAT_EVENTS_TEXT,
        GENERAL_CHAT_PROFILE_TEXT,
    ]
    assert GENERAL_CHAT_EVENTS_TEXT == "📅 События"
    assert GENERAL_CHAT_PROFILE_TEXT == "🔥 Моя ЭРА"


def test_group_event_link_opens_exact_main_miniapp_route() -> None:
    assert telegram_event_miniapp_url("@ERA_1bot", 29) == (
        "https://t.me/ERA_1bot?startapp=event_29"
    )


def test_group_profile_link_opens_profile_route() -> None:
    assert telegram_profile_miniapp_url("ERA_1bot") == (
        "https://t.me/ERA_1bot?startapp=profile"
    )
