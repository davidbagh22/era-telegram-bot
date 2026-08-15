from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.utils.deep_links import bot_start_deep_link


FAQ_BUTTONS = (
    ("🔥 Что такое ЭРА", "faq_what_is_era", "faq:what_is_era"),
    ("🚀 Как здесь расти", "faq_what_it_gives", "faq:what_it_gives"),
    ("🧭 С чего начать", "faq_what_to_do", "faq:what_to_do"),
    ("💡 Как предложить идею", "faq_what_can_i_do", "faq:what_can_i_do"),
    ("💬 Задать вопрос", "faq_contact", "faq:contact"),
)


def faq_keyboard(bot_username: str = "") -> InlineKeyboardMarkup:
    """Fast private-help actions attached to the pinned general-chat FAQ.

    With a bot username these are normal t.me /start links, so Telegram opens
    the participant's private chat immediately instead of leaving them in the
    group with a callback toast. Callback data remains a safe fallback for
    local/test deployments where the username is not configured yet.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for text, start_payload, callback_data in FAQ_BUTTONS:
        url = bot_start_deep_link(bot_username, start_payload)
        button = (
            InlineKeyboardButton(text=text, url=url)
            if url
            else InlineKeyboardButton(text=text, callback_data=callback_data)
        )
        rows.append([button])
    return InlineKeyboardMarkup(inline_keyboard=rows)
