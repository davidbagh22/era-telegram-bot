from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)

GENERAL_CHAT_EVENTS_TEXT = "📅 События"
GENERAL_CHAT_PROFILE_TEXT = "👤 Мой профиль"


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


def general_chat_navigation_keyboard() -> ReplyKeyboardRemove:
    """Actively clear the retired persistent group dock from Telegram clients."""
    return ReplyKeyboardRemove(remove_keyboard=True)
