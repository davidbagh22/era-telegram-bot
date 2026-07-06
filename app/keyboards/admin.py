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
            ("Проекты", "admin:projects"),
            ("Мероприятия", "admin:events"),
            ("Активности после мероприятий", "admin:event_activities"),
            ("Задания и конкурсы", "admin:tasks"),
        )
    )


def admin_communications_keyboard() -> InlineKeyboardMarkup:
    return _submenu(
        (
            ("Вопросы пользователей", "admin:questions"),
            ("Создать рассылку", "admin:broadcast"),
            ("Приветствия в чатах", "admin:greetings"),
        )
    )


def admin_growth_keyboard() -> InlineKeyboardMarkup:
    return _submenu(
        (
            ("Начислить баллы или знак", "admin:points"),
            ("Каталог возможностей", "admin:rewards"),
            ("Партнёры", "admin:partners"),
            ("Аукционы", "admin:auctions"),
            ("Портфолио и сертификаты", "admin:portfolio"),
            ("Предложения лидеров", "admin:proposals"),
        )
    )


def admin_system_keyboard() -> InlineKeyboardMarkup:
    return _submenu(
        (
            ("Должности и права", "admin:offices"),
            ("Аналитика и Excel", "admin:analytics"),
            ("Настройки", "admin:settings"),
            ("Очистка тестовых данных", "admin:maintenance"),
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
                    text="✅ Одобрить", callback_data=f"admin:approve_user:{user_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"admin:reject_user:{user_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💬 Задать уточняющий вопрос",
                    callback_data=f"admin:info_user:{user_id}",
                )
            ],
            [InlineKeyboardButton(text="Открыть заявку", callback_data=f"admin:application:{user_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="admin:applications")],
        ]
    )


def people_filters_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔎 Найти человека", callback_data="admin:people:search"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Все", callback_data="admin:people:list:all:0:0"
                ),
                InlineKeyboardButton(
                    text="По роли", callback_data="admin:people:roles"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="По возрасту", callback_data="admin:people:ages"
                ),
                InlineKeyboardButton(
                    text="По городу", callback_data="admin:people:cities"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="По направлению", callback_data="admin:people:directions"
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:menu:users")],
        ]
    )


def role_filters_keyboard() -> InlineKeyboardMarkup:
    options = (
        ("Участники", "participant"),
        ("Активисты", "activist"),
        ("Лидеры", "leader"),
        ("Руководители", "head"),
        ("Совет", "council"),
        ("Администраторы", "admin"),
    )
    rows = [
        [
            InlineKeyboardButton(
                text=label, callback_data=f"admin:people:list:role:{value}:0"
            )
        ]
        for label, value in options
    ]
    rows.append(
        [InlineKeyboardButton(text="← К фильтрам", callback_data="admin:participants")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def age_filters_keyboard() -> InlineKeyboardMarkup:
    options = (
        ("14–17 лет", "14_17"),
        ("18–24 года", "18_24"),
        ("25–34 года", "25_34"),
        ("35 лет и старше", "35_plus"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label, callback_data=f"admin:people:list:age:{value}:0"
                )
            ]
            for label, value in options
        ]
        + [
            [
                InlineKeyboardButton(
                    text="← К фильтрам", callback_data="admin:participants"
                )
            ]
        ]
    )
