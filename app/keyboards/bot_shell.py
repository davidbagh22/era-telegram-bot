from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.keyboards.participant import main_inline_keyboard as legacy_main_inline_keyboard
from app.utils.deep_links import miniapp_admin_url, miniapp_leader_url


def main_inline_keyboard(
    privileged: bool = False,
    admin: bool = False,
    miniapp_url: str = "",
) -> InlineKeyboardMarkup:
    """Primary bot shell.

    The Mini App stays the main workspace, while Telegram keeps the few actions
    that are genuinely useful in-chat: My Vector, role workspace shortcuts and
    contact. The legacy participant keyboard remains the emergency/fallback
    implementation and is deliberately not deleted.
    """
    base = legacy_main_inline_keyboard(
        privileged=privileged,
        admin=admin,
        miniapp_url=miniapp_url,
    )
    rows = [list(row) for row in base.inline_keyboard]

    vector_row = [
        InlineKeyboardButton(text="🧭 Мой вектор", callback_data="vector:home")
    ]

    if miniapp_url:
        # Current base order is Open ERA -> Navigation -> Contact. Keep the
        # primary app entry first and place native, personal action right below.
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
        # Local/emergency mode has no Mini App, so My Vector remains reachable
        # while the old cabinet/events/tasks tree continues to work unchanged.
        rows.insert(max(0, len(rows) - 1), vector_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)
