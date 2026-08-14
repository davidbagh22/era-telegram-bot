from collections.abc import Iterable

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)

from app.utils.deep_links import (
    miniapp_admin_url,
    miniapp_community_url,
    miniapp_events_url,
    miniapp_leader_url,
    miniapp_opportunities_url,
    miniapp_profile_url,
    miniapp_projects_url,
    miniapp_tasks_url,
)


def main_inline_keyboard(
    privileged: bool = False, admin: bool = False, miniapp_url: str = ""
) -> InlineKeyboardMarkup:
    """The bot's one and only main gateway surface."""
    rows: list[list[InlineKeyboardButton]] = []
    if miniapp_url:
        rows.append(
            [InlineKeyboardButton(text="🔥 Открыть ЭРА", web_app=WebAppInfo(url=miniapp_url))]
        )
        rows.append([InlineKeyboardButton(text="🧭 Навигация", callback_data="nav:guide")])
    else:
        rows.append(
            [
                InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet:open"),
                InlineKeyboardButton(text="📅 Афиша", callback_data="events:list"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="✅ Задачи", callback_data="cabinet:tasks"),
                InlineKeyboardButton(text="⭐ Возможности", callback_data="offers:menu"),
            ]
        )
        if privileged or admin:
            rows.append([InlineKeyboardButton(text="⚙️ Панель", callback_data="panel:open")])
    rows.append([InlineKeyboardButton(text="💬 Связь", callback_data="contact:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def open_app_button(
    miniapp_url: str, label: str = "Открыть в приложении ЭРА"
) -> InlineKeyboardMarkup | None:
    if not miniapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=miniapp_url))]]
    )


def navigation_guide_keyboard(
    miniapp_url: str, admin: bool = False, privileged: bool = False
) -> InlineKeyboardMarkup:
    """Build all Navigation destinations from one base Mini App URL.

    External Telegram WebApp links use query routes (``eraPath``), not URL
    fragments. Keeping route construction here prevents callers from passing a
    partially-routed URL and makes participant/Admin/Leader buttons obey one
    contract.
    """
    rows = [
        [
            InlineKeyboardButton(
                text="Проекты", web_app=WebAppInfo(url=miniapp_projects_url(miniapp_url))
            ),
            InlineKeyboardButton(
                text="События", web_app=WebAppInfo(url=miniapp_events_url(miniapp_url))
            ),
        ],
        [
            InlineKeyboardButton(
                text="Сообщество",
                web_app=WebAppInfo(url=miniapp_community_url(miniapp_url)),
            ),
            InlineKeyboardButton(
                text="Профиль", web_app=WebAppInfo(url=miniapp_profile_url(miniapp_url))
            ),
        ],
        [
            InlineKeyboardButton(
                text="Мои задачи", web_app=WebAppInfo(url=miniapp_tasks_url(miniapp_url))
            ),
            InlineKeyboardButton(
                text="Возможности", web_app=WebAppInfo(url=miniapp_opportunities_url(miniapp_url))
            ),
        ],
    ]
    if admin:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⚙️ Режим администратора",
                    web_app=WebAppInfo(url=miniapp_admin_url(miniapp_url)),
                )
            ]
        )
    elif privileged:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🧭 Режим лидера",
                    web_app=WebAppInfo(url=miniapp_leader_url(miniapp_url)),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="💬 Связь", callback_data="contact:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def about_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet:open")],
            [InlineKeyboardButton(text="📅 Афиша", callback_data="events:list")],
            [InlineKeyboardButton(text="✅ Задачи", callback_data="cabinet:tasks")],
            [InlineKeyboardButton(text="💡 Проекты", callback_data="projects:menu")],
            [InlineKeyboardButton(text="⭐ Возможности", callback_data="offers:menu")],
            [InlineKeyboardButton(text="💬 Связь", callback_data="contact:menu")],
        ]
    )


def contact_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❓ Задать вопрос", callback_data="question:start")],
            [InlineKeyboardButton(text="👥 Команда ЭРА", callback_data="team:menu")],
            [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about:open")],
            [InlineKeyboardButton(text="📜 Правила", callback_data="rules:open")],
            [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
        ]
    )


def team_keyboard(general_chat_url: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🏛 Департаменты", callback_data="departments:menu")],
        [InlineKeyboardButton(text="📞 К кому обратиться", callback_data="team:offices")],
        [InlineKeyboardButton(text="👤 Руководители направлений", callback_data="team:offices")],
        [InlineKeyboardButton(text="💬 Чаты департаментов", callback_data="department:chats")],
    ]
    if general_chat_url:
        rows.append([InlineKeyboardButton(text="💬 Общий чат ЭРА", url=general_chat_url)])
    rows.append([InlineKeyboardButton(text="← Связь", callback_data="contact:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def journey_keyboard(
    internal_chat_url: str | None = None, external_chat_url: str | None = None
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📈 Мой путь", callback_data="cabinet:journey")],
        [InlineKeyboardButton(text="🏆 Рейтинг", callback_data="rating:open")],
        [InlineKeyboardButton(text="🎖 Достижения", callback_data="badges:open")],
        [InlineKeyboardButton(text="📁 Портфолио", callback_data="portfolio:open")],
        [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_list_keyboard(events: Iterable) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=event.title, callback_data=f"event:open:{event.id}")]
        for event in events
    ]
    rows.append([InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
