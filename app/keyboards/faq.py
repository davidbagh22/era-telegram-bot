from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

GENERAL_CHAT_EVENTS_TEXT = "📅 События"
GENERAL_CHAT_PROFILE_TEXT = "👤 Мой профиль"


def faq_keyboard() -> InlineKeyboardMarkup:
    """Fast private-help and navigation actions attached to the pinned general-chat FAQ."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=GENERAL_CHAT_EVENTS_TEXT, callback_data="faq:events"),
                InlineKeyboardButton(text=GENERAL_CHAT_PROFILE_TEXT, callback_data="faq:profile"),
            ],
            [InlineKeyboardButton(text="🔥 Что такое ЭРА", callback_data="faq:what_is_era")],
            [InlineKeyboardButton(text="🚀 Как здесь расти", callback_data="faq:what_it_gives")],
            [InlineKeyboardButton(text="🧭 С чего начать", callback_data="faq:what_to_do")],
            [InlineKeyboardButton(text="💡 Как предложить идею", callback_data="faq:what_can_i_do")],
            [InlineKeyboardButton(text="💬 Задать вопрос", callback_data="faq:contact")],
        ]
    )


def general_chat_navigation_keyboard() -> ReplyKeyboardMarkup:
    """Persistent two-button dock shown under the composer in the general chat.

    Telegram only permits text reply-keyboard buttons in groups; Web App keyboard
    buttons are private-chat only. Presses are intercepted by app.handlers.chat,
    removed from the group, and converted into a private Web App deep link so the
    shared chat stays clean.
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
