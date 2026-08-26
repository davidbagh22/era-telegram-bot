from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.keyboards.participant import (
    main_inline_keyboard as legacy_main_inline_keyboard,
    navigation_guide_keyboard as legacy_navigation_guide_keyboard,
)


def main_inline_keyboard(
    privileged: bool = False,
    admin: bool = False,
    miniapp_url: str = "",
) -> InlineKeyboardMarkup:
    """Primary bot shell: gateway, not a second application.

    With Mini App configured the authoritative participant keyboard already
    contains exactly three actions: 🔥 Открыть ЭРА, 🧭 Навигация and 💬 Связь.
    Admin/leader tools and Мой вектор live inside the app/navigation guide, so
    the /start surface never grows into a parallel dashboard again.
    """
    return legacy_main_inline_keyboard(
        privileged=privileged,
        admin=admin,
        miniapp_url=miniapp_url,
    )


def navigation_guide_keyboard(
    miniapp_url: str,
    admin: bool = False,
    privileged: bool = False,
) -> InlineKeyboardMarkup:
    base = legacy_navigation_guide_keyboard(
        miniapp_url,
        admin=admin,
        privileged=privileged,
    )
    rows = [list(row) for row in base.inline_keyboard]
    # My Vector remains a contextual/deep-link destination, not a fourth main
    # bot action or sixth participant bottom-nav item.
    rows.insert(0, [InlineKeyboardButton(text="🧭 Мой вектор", callback_data="vector:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def contact_keyboard() -> InlineKeyboardMarkup:
    """Compact service centre: every button has one clear destination."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❓ Задать вопрос", callback_data="question:start")],
            [InlineKeyboardButton(text="👥 Кто за что отвечает", callback_data="team:menu")],
            [
                InlineKeyboardButton(text="🏛 Департаменты", callback_data="departments:menu"),
                InlineKeyboardButton(text="💬 Чаты", callback_data="department:chats"),
            ],
            [
                InlineKeyboardButton(text="📜 Правила", callback_data="rules:open"),
                InlineKeyboardButton(text="ℹ️ О боте", callback_data="about:open"),
            ],
            [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
        ]
    )


def team_keyboard(general_chat_url: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📞 К кому обратиться", callback_data="team:offices")],
        [InlineKeyboardButton(text="🏛 Департаменты и направления", callback_data="departments:menu")],
        [InlineKeyboardButton(text="💬 Чаты департаментов", callback_data="department:chats")],
    ]
    if general_chat_url:
        rows.append([InlineKeyboardButton(text="💬 Общий чат ЭРА", url=general_chat_url)])
    rows.append([InlineKeyboardButton(text="← Связь", callback_data="contact:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
