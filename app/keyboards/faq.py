from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

GENERAL_CHAT_EVENTS_TEXT = "📅 Мероприятия"
GENERAL_CHAT_PROFILE_TEXT = "👤 Моя ЭРА"


def _private_url(bot_username: str, payload: str) -> str:
    return f"https://t.me/{bot_username}?start={payload}"


def faq_keyboard(bot_username: str | None = None) -> InlineKeyboardMarkup:
    """Pinned general-chat FAQ. Every action opens a private bot deep link."""
    items = [
        ("📅 Ближайшие события", "faq_events", "faq:events"),
        ("🚀 Мои проекты", "faq_projects", "faq:projects"),
        ("✅ Мои задания", "faq_tasks", "faq:tasks"),
        ("⭐ Баллы и возможности", "faq_points", "faq:points"),
        ("🙋 Как зарегистрироваться", "faq_registration", "faq:registration"),
        ("🔥 Как стать активным", "faq_active", "faq:active"),
        ("💬 Связаться с командой", "faq_contact", "faq:contact"),
    ]
    rows = []
    for label, payload, callback in items:
        if bot_username:
            rows.append([InlineKeyboardButton(text=label, url=_private_url(bot_username, payload))])
        else:
            rows.append([InlineKeyboardButton(text=label, callback_data=callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def general_chat_navigation_keyboard() -> ReplyKeyboardMarkup:
    """Persistent two-button navigation bar shown above the group text field."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=GENERAL_CHAT_EVENTS_TEXT),
                KeyboardButton(text=GENERAL_CHAT_PROFILE_TEXT),
            ]
        ],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите раздел ЭРА",
    )
