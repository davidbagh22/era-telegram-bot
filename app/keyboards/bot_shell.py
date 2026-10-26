from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.keyboards.participant import (
    main_inline_keyboard as legacy_main_inline_keyboard,
    navigation_guide_keyboard as legacy_navigation_guide_keyboard,
)
from app.utils.deep_links import miniapp_admin_url, miniapp_leader_url
from app.utils.constants import PRIVILEGED_ROLES
from app.services.leadership_permission_service import is_assignment_active


def has_leaders_entry(user) -> bool:
    return bool(user and (user.role in PRIVILEGED_ROLES or any(
        is_assignment_active(a) for a in user.__dict__.get("office_assignments", []))))


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
    rows.insert(1 if rows else 0, [InlineKeyboardButton(text="🎲 Досуг", callback_data="leisure:home")])

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


def main_reply_keyboard(miniapp_url: str = "", *, admin: bool = False, leaders: bool = False, media_chair: bool = False) -> ReplyKeyboardMarkup:
    """Persistent quick-access menu shown above the Telegram input field."""
    rows: list[list[KeyboardButton]] = []
    if miniapp_url:
        rows.append([
            # Reply-keyboard WebApps use Telegram's simple mode, which has
            # no signed initData. Send a normal message so the handler can
            # offer an authenticated inline WebApp button instead.
            KeyboardButton(text="🔥 Открыть ЭРА"),
            KeyboardButton(text="🧭 Навигация"),
        ])
    else:
        rows.append([
            KeyboardButton(text="👤 Личный кабинет"),
            KeyboardButton(text="📅 Афиша"),
        ])
        rows.append([
            KeyboardButton(text="⭐ Возможности"),
            KeyboardButton(text="🧭 Навигация"),
        ])
    if admin:
        rows.append([
            KeyboardButton(text="📊 Статистика"),
            KeyboardButton(text="📥 Заявки"),
        ])
    if leaders or admin:
        rows.append([KeyboardButton(text="🧭 Лидеры")])
    if media_chair:
        rows.append([KeyboardButton(text="🎬 Руководитель медиа")])
    rows.append([
        KeyboardButton(text="💬 Связь"),
        KeyboardButton(text="🎲 Досуг"),
    ])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите раздел ЭРА",
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
    rows.insert(0, [InlineKeyboardButton(text="🧭 Мой вектор", callback_data="vector:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def contact_keyboard(back_callback: str | None = None, *, support_threads: bool = False) -> InlineKeyboardMarkup:
    """Compact service centre: every button has one clear destination."""
    markup = InlineKeyboardMarkup(
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

    if support_threads:
        markup.inline_keyboard.insert(1, [InlineKeyboardButton(text='💬 Мои обращения', callback_data='support:mine:page:0')])
    if back_callback:
        markup.inline_keyboard.insert(-1, [InlineKeyboardButton(text="← К вопросам", callback_data=back_callback)])
    return markup


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
