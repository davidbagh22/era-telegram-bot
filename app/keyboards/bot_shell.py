from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.keyboards.participant import (
    main_inline_keyboard as legacy_main_inline_keyboard,
    navigation_guide_keyboard as legacy_navigation_guide_keyboard,
)
from app.utils.deep_links import miniapp_admin_url, miniapp_leader_url


def main_inline_keyboard(
    privileged: bool = False,
    admin: bool = False,
    miniapp_url: str = "",
) -> InlineKeyboardMarkup:
    """Primary bot shell without duplicating the Mini App workspace."""
    base = legacy_main_inline_keyboard(
        privileged=privileged,
        admin=admin,
        miniapp_url=miniapp_url,
    )
    rows = [list(row) for row in base.inline_keyboard]
    vector_row = [InlineKeyboardButton(text="🧭 Мой вектор", callback_data="vector:home")]

    if miniapp_url:
        insert_at = 1 if rows else 0
        rows.insert(insert_at, vector_row)
        insert_at += 1
        if admin:
            rows.insert(
                insert_at,
                [
                    InlineKeyboardButton(
                        text="⚙️ Управление ЭРА",
                        web_app=WebAppInfo(url=miniapp_admin_url(miniapp_url)),
                    )
                ],
            )
        elif privileged:
            rows.insert(
                insert_at,
                [
                    InlineKeyboardButton(
                        text="🧭 Режим лидера",
                        web_app=WebAppInfo(url=miniapp_leader_url(miniapp_url)),
                    )
                ],
            )
    else:
        # Emergency/local mode keeps the old bot tree intact and adds only the
        # Telegram-native self-development entry.
        rows.insert(max(0, len(rows) - 1), vector_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    rows.insert(0, [InlineKeyboardButton(text="🧭 Мой вектор", callback_data="vector:home")])
    if admin or privileged:
        # QR is generated in Telegram because leaders need a fast operational
        # action at the venue; scanning remains a normal /start deep link.
        rows.insert(
            max(1, len(rows) - 1),
            [InlineKeyboardButton(text="🎟 QR вход на событие", callback_data="event_qr:help")],
        )
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
