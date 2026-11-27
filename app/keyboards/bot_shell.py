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
from app.services.anniversary_registration_service import MENU_BUTTON, MENU_TICKET_BUTTON
from app.utils.deep_links import miniapp_admin_section_url, miniapp_admin_url, miniapp_leader_url
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


ADMIN_HUB_BUTTON = "⚙️ Админ"
OPEN_APP_BUTTON = "🔥 Открыть ЭРА"
HELP_BUTTON = "❓ Помощь"
HELP_BUTTON_ALIASES = frozenset({HELP_BUTTON, "Помощь", "помощь", "🆘 Помощь"})

# Texts of every reply-keyboard button the bot has ever shown. Users with an
# old persistent keyboard can still tap them, so the handlers behind each text
# must stay registered even though the keyboard itself is now two buttons.
LEGACY_REPLY_BUTTON_TEXTS = frozenset({
    "🔥 Открыть ЭРА", "📅 Афиша", "📅 Мероприятия", "🌱 Мой путь", "⭐ Возможности",
    "👤 Личный кабинет", "💬 Связь", "🧭 Лидеры", "🧭 Панель лидера", "🎬 Медиа",
    "⚙️ Админ", "💡 Проекты", "✅ Задачи", "🏆 Рейтинг", "🧭 Навигация", "🧭 Главное меню",
    "⚙️ Панель", "❓ Вопросы об ЭРА", "❓ Вопросы и связь", "🎲 Досуг", "📖 Книжный клуб",
    "🤝 Партнёры", "🤝 Команда ЭРА", "ℹ️ О боте", "💬 Задать вопрос", "💬 Мои обращения",
    "📊 Статистика", "📊 Админ-сводка", "📥 Заявки", "⚙️ Управление",
    "🎟 Зарегистрироваться на годовщину", "🎟 Годовщина · я в списке",
})


def main_reply_keyboard(
    miniapp_url: str = "", *, admin: bool = False, leaders: bool = False,
    media_chair: bool = False, anniversary: bool = False,
    anniversary_registered: bool = False,
) -> ReplyKeyboardMarkup:
    """Persistent menu above the Telegram input field: exactly two buttons.

    «Открыть ЭРА» opens the Mini App, «Помощь» opens the inline hub with every
    other section and the role shortcuts (leaders, media, admin, anniversary).
    The role/anniversary arguments are accepted so existing callers keep
    working; they no longer change the keyboard — those entries live as inline
    buttons under the «Помощь» message instead.
    """
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=OPEN_APP_BUTTON), KeyboardButton(text=HELP_BUTTON)]],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Откройте ЭРА или нажмите «Помощь»",
    )


def anniversary_inline_keyboard(registered: bool = False) -> InlineKeyboardMarkup:
    label = MENU_TICKET_BUTTON if registered else MENU_BUTTON
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data="anniversary:menu")]])


def help_hub_keyboard(
    miniapp_url: str = "",
    *,
    admin: bool = False,
    leaders: bool = False,
    media_chair: bool = False,
    anniversary: bool = False,
    anniversary_registered: bool = False,
    privileged: bool = False,
) -> InlineKeyboardMarkup:
    """Everything the old reply keyboard offered, as inline buttons."""
    rows: list[list[InlineKeyboardButton]] = []
    if anniversary:
        label = MENU_TICKET_BUTTON if anniversary_registered else MENU_BUTTON
        rows.append([InlineKeyboardButton(text=label, callback_data="anniversary:menu")])
    rows.extend([
        [
            InlineKeyboardButton(text="📅 Афиша", callback_data="events:list"),
            InlineKeyboardButton(text="🌱 Мой путь", callback_data="cabinet:open"),
        ],
        [
            InlineKeyboardButton(text="⭐ Возможности", callback_data="offers:menu"),
            InlineKeyboardButton(text="💬 Связь", callback_data="contact:menu"),
        ],
        [
            InlineKeyboardButton(text="🧭 Мой вектор", callback_data="vector:home"),
            InlineKeyboardButton(text="🎲 Досуг", callback_data="leisure:home"),
        ],
        [InlineKeyboardButton(text="❓ Вопросы об ЭРА", callback_data="faq:home")],
    ])
    role_row: list[InlineKeyboardButton] = []
    if leaders:
        role_row.append(InlineKeyboardButton(text="🧭 Лидеры", callback_data="wc:home"))
    if media_chair:
        role_row.append(InlineKeyboardButton(text="🎬 Медиа", callback_data="media:leader"))
    if role_row:
        rows.append(role_row)
    if admin:
        rows.append([InlineKeyboardButton(text=ADMIN_HUB_BUTTON, callback_data="admin:hub:open")])
    elif privileged and miniapp_url:
        rows.append([InlineKeyboardButton(text="🧭 Режим лидера", web_app=WebAppInfo(url=miniapp_leader_url(miniapp_url)))])
    rows.append([InlineKeyboardButton(text="🧭 Навигация по ЭРА", callback_data="nav:guide")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_hub_keyboard(
    miniapp_url: str = "", *, pending: int | None = None, expanded: bool = False,
) -> InlineKeyboardMarkup:
    """Light admin hub: «Мероприятия», «Заявки · N», «Задачи» and «Ещё».

    «Ещё» swaps the keyboard for the secondary tools (nothing was removed:
    statistics and the full Mini App admin moved there)."""
    applications = "📥 Заявки" if not pending else f"📥 Заявки · {pending}"
    if expanded:
        rows = [
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:management:open")],
        ]
        if miniapp_url:
            rows.append([InlineKeyboardButton(
                text="⚙️ Управление ЭРА", web_app=WebAppInfo(url=miniapp_admin_url(miniapp_url)),
            )])
        rows.append([InlineKeyboardButton(text="🧭 Лидеры", callback_data="wc:home")])
        rows.append([InlineKeyboardButton(text="← Назад", callback_data="admin:hub:home")])
        rows.append([InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    if miniapp_url:
        events_button = InlineKeyboardButton(
            text="🎉 Мероприятия",
            web_app=WebAppInfo(url=miniapp_admin_section_url(miniapp_url, "events")),
        )
    else:
        events_button = InlineKeyboardButton(text="🎉 Мероприятия", callback_data="events:list")
    rows = [
        [events_button],
        [InlineKeyboardButton(text=applications, callback_data="admin:applications")],
        [InlineKeyboardButton(text="✅ Задачи", callback_data="admin:tasks")],
        [InlineKeyboardButton(text="⋯ Ещё", callback_data="admin:hub:more")],
    ]
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
    return InlineKeyboardMarkup(inline_keyboard=rows)


def contact_keyboard(back_callback: str | None = None, *, support_threads: bool = False) -> InlineKeyboardMarkup:
    """Compact service centre: primary actions first, then structure."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="❓ Задать вопрос", callback_data="question:start")],
    ]
    if support_threads:
        rows.append([InlineKeyboardButton(text="💬 Мои обращения", callback_data="support:mine:page:0")])
    rows.extend([
        [InlineKeyboardButton(text="👥 Кто за что отвечает", callback_data="team:menu")],
        [
            InlineKeyboardButton(text="🏛 Департаменты", callback_data="departments:menu"),
            InlineKeyboardButton(text="💬 Чаты", callback_data="department:chats"),
        ],
        [
            InlineKeyboardButton(text="📜 Правила", callback_data="rules:open"),
            InlineKeyboardButton(text="ℹ️ О боте", callback_data="about:open"),
        ],
    ])
    if back_callback:
        rows.append([InlineKeyboardButton(text="← К вопросам", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
