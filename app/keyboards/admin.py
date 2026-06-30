from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    options = (
        ("Заявки", "admin:applications"),
        ("Участники", "admin:participants"),
        ("Роли и статусы", "admin:roles"),
        ("Департаменты и направления", "admin:departments"),
        ("Мероприятия", "admin:events"),
        ("Селфи на проверке", "admin:attendance"),
        ("Проекты", "admin:projects"),
        ("Баллы и знаки", "admin:points"),
        ("Портфолио участников", "admin:portfolio"),
        ("Задачи на проверке", "admin:tasks"),
        ("Предложения лидеров", "admin:proposals"),
        ("Вопросы пользователей", "admin:questions"),
        ("Рассылки", "admin:broadcast"),
        ("Рассылки лидеров", "admin:leader_broadcasts"),
        ("Отчёты", "admin:reports"),
        ("Аналитика", "admin:analytics"),
        ("Настройки", "admin:settings"),
        ("Главное меню", "menu:main"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=callback)]
            for label, callback in options
        ]
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
