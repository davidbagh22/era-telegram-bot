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


def faq_home_keyboard() -> InlineKeyboardMarkup:
    from app.content.era_faq import FAQ_CATEGORIES

    buttons = [InlineKeyboardButton(text=item["title"], callback_data=f"faq:cat:{key}")
               for key, item in FAQ_CATEGORIES.items()]
    rows = [buttons[:2], *[[button] for button in buttons[2:]]]
    rows.extend([
        [InlineKeyboardButton(text="💬 Связаться с ЭРА", callback_data="contact:menu")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_faq_answer_keyboard(back_callback: str, action: str | None = None) -> InlineKeyboardMarkup:
    from app.content.era_faq import FAQ_ACTIONS

    rows = []
    if action in FAQ_ACTIONS:
        label, callback = FAQ_ACTIONS[action]
        rows.append([InlineKeyboardButton(text=label, callback_data=callback)])
    rows.extend([
        [InlineKeyboardButton(text="💬 Связаться с ЭРА", callback_data="contact:menu")],
        [InlineKeyboardButton(text="← К вопросам", callback_data=back_callback),
         InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faq_category_keyboard(category_id: str) -> InlineKeyboardMarkup:
    from app.content.era_faq import FAQ_CATEGORIES, FAQ_DATA

    rows = [[InlineKeyboardButton(text=FAQ_DATA[q]["title"], callback_data=f"faq:q:{q}")]
            for q in FAQ_CATEGORIES[category_id]["questions"] if q in FAQ_DATA]
    rows.extend([
        [InlineKeyboardButton(text="💬 Связаться с ЭРА", callback_data="contact:menu")],
        [InlineKeyboardButton(text="← Все темы", callback_data="faq:home"),
         InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
