from aiogram.types import ReplyKeyboardRemove

from app.keyboards.faq import general_chat_navigation_keyboard
from app.utils.deep_links import (
    telegram_event_miniapp_url,
    telegram_profile_miniapp_url,
)


def test_general_chat_navigation_removes_legacy_reply_keyboard() -> None:
    keyboard = general_chat_navigation_keyboard()

    assert isinstance(keyboard, ReplyKeyboardRemove)
    assert keyboard.remove_keyboard is True


def test_group_event_link_opens_exact_main_miniapp_route() -> None:
    assert telegram_event_miniapp_url("@ERA_1bot", 29) == (
        "https://t.me/ERA_1bot?startapp=event_29"
    )


def test_group_profile_link_opens_profile_route() -> None:
    assert telegram_profile_miniapp_url("ERA_1bot") == (
        "https://t.me/ERA_1bot?startapp=profile"
    )
