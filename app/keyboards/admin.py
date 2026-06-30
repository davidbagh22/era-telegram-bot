from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 Участники", callback_data="admin:menu:users"
                ),
                InlineKeyboardButton(
                    text="📅 События", callback_data="admin:menu:activity"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💬 Общение", callback_data="admin:menu:communications"
                ),
                InlineKeyboardButton(
                    text="⭐ Развитие", callback_data="admin:menu:growth"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📊 Управление", callback_data="admin:menu:system"
                ),
                InlineKeyboardButton(text="🏠 Главное", callback_data="menu:main"),
            ],
        ]
    )


def _submenu(options: tuple[tuple[str, str], ...]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=callback)]
        for label, callback in options
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_users_keyboard() -> InlineKeyboardMarkup:
    return _submenu(
        (
            ("Новые заявки", "admin:applications"),
            ("Все участники", "admin:participants"),
            ("Роли и статусы", "admin:roles"),
            ("Департаменты", "admin:departments"),
        )
    )


def admin_activity_keyboard() -> InlineKeyboardMarkup:
    return _submenu(
        (
            ("Мероприятия", "admin:events"),
            ("Селфи на проверке", "admin:attendance"),
            ("Проекты", "admin:projects"),
            ("Задачи на проверке", "admin:tasks"),
            ("Отчёты", "admin:reports"),
        )
    )


def admin_communications_keyboard() -> InlineKeyboardMarkup:
    return _submenu(
        (
            ("Вопросы пользователей", "admin:questions"),
            ("Рассылка участникам", "admin:broadcast"),
            ("Рассылки лидеров", "admin:leader_broadcasts"),
        )
    )


def admin_growth_keyboard() -> InlineKeyboardMarkup:
    return _submenu(
        (
            ("Баллы и знаки", "admin:points"),
            ("Портфолио участников", "admin:portfolio"),
            ("Предложения лидеров", "admin:proposals"),
        )
    )


def admin_system_keyboard() -> InlineKeyboardMarkup:
    return _submenu(
        (
            ("Аналитика", "admin:analytics"),
            ("Настройки", "admin:settings"),
        )
    )


def applications_keyboard(users: Iterable) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{user.first_name} {user.last_name or ''}",
                callback_data=f"admin:application:{user.id}",
            )
        ]
        for user in users
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def application_actions(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Одобрить", callback_data=f"admin:approve_user:{user_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Запросить информацию",
                    callback_data=f"admin:info_user:{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отклонить", callback_data=f"admin:reject_user:{user_id}"
                )
            ],
            [InlineKeyboardButton(text="Назад", callback_data="admin:applications")],
        ]
    )


def entity_actions(kind: str, entity_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Одобрить", callback_data=f"admin:{kind}:approve:{entity_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="На доработку",
                    callback_data=f"admin:{kind}:revise:{entity_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отклонить", callback_data=f"admin:{kind}:reject:{entity_id}"
                )
            ],
        ]
    )
