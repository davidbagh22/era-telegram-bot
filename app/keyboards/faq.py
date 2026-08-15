from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.utils.deep_links import bot_start_deep_link

GENERAL_CHAT_EVENTS_TEXT = "📅 События"
GENERAL_CHAT_PROFILE_TEXT = "👤 Мой профиль"

FAQ_BUTTONS = (
    ("🔥 Что такое ЭРА", "faq_what_is_era", "faq:what_is_era"),
    ("🚀 Как здесь расти", "faq_what_it_gives", "faq:what_it_gives"),
    ("🧭 С чего начать", "faq_what_to_do", "faq:what_to_do"),
    ("💡 Как предложить идею", "faq_what_can_i_do", "faq:what_can_i_do"),
    ("💬 Задать вопрос", "faq_contact", "faq:contact"),
)


def faq_keyboard(bot_username: str = "") -> InlineKeyboardMarkup:
    """Pinned FAQ: navigation plus private help actions.

    Events/profile keep the general-chat callbacks that privately hand off to
    the exact Mini App screen. FAQ questions use t.me /start links when the bot
    username is available, so tapping them opens the private bot dialog
    immediately. Callback data remains a safe fallback for test/local setups.
    """
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=GENERAL_CHAT_EVENTS_TEXT, callback_data="faq:events"),
            InlineKeyboardButton(text=GENERAL_CHAT_PROFILE_TEXT, callback_data="faq:profile"),
        ]
    ]
    for text, start_payload, callback_data in FAQ_BUTTONS:
        url = bot_start_deep_link(bot_username, start_payload)
        rows.append([
            InlineKeyboardButton(text=text, url=url)
            if url
            else InlineKeyboardButton(text=text, callback_data=callback_data)
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def general_chat_navigation_keyboard() -> ReplyKeyboardMarkup:
    """Persistent two-button dock shown under the composer in the general chat.

    Telegram only permits text reply-keyboard buttons in groups; presses are
    intercepted by app.handlers.chat, removed from the group, and converted
    into a private exact-screen Mini App handoff.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=GENERAL_CHAT_EVENTS_TEXT),
                KeyboardButton(text=GENERAL_CHAT_PROFILE_TEXT),
            ]
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Быстрый доступ ЭРА",
    )
