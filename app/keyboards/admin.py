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


def people_list_keyboard(
    users: Iterable,
    *,
    kind: str,
    value: str,
    page: int,
    has_next: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{person.first_name} {person.last_name or ''}".strip(),
                callback_data=f"admin:user:{person.id}",
            )
        ]
        for person in users
    ]
    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="←", callback_data=f"admin:people:list:{kind}:{value}:{page - 1}"
            )
        )
    if has_next:
        navigation.append(
            InlineKeyboardButton(
                text="→", callback_data=f"admin:people:list:{kind}:{value}:{page + 1}"
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append(
        [InlineKeyboardButton(text="← К фильтрам", callback_data="admin:participants")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_actions(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Изменить роль", callback_data=f"admin:user:role:{user_id}"
                ),
                InlineKeyboardButton(
                    text="Изменить статус", callback_data=f"admin:user:status:{user_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Портфолио", callback_data=f"admin:user:portfolio:{user_id}"
                ),
                InlineKeyboardButton(
                    text="Баллы и бейджи", callback_data="admin:points"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Удалить участника",
                    callback_data=f"admin:user:archive:{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="← К списку", callback_data="admin:participants"
                )
            ],
        ]
    )


def user_role_keyboard(user_id: int) -> InlineKeyboardMarkup:
    options = (
        ("Участник", "participant"),
        ("Активист", "activist"),
        ("Лидер", "leader"),
        ("Руководитель", "head"),
        ("Совет", "council"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"admin:user:setrole:{user_id}:{value}",
                )
            ]
            for label, value in options
        ]
        + [
            [
                InlineKeyboardButton(
                    text="← Назад", callback_data=f"admin:user:{user_id}"
                )
            ]
        ]
    )


def user_status_keyboard(user_id: int) -> InlineKeyboardMarkup:
    options = (
        ("Новый участник", "new_member"),
        ("Вовлечённый участник", "involved_member"),
        ("Активный участник", "active_member"),
        ("Член команды", "team_member"),
        ("Куратор проекта", "project_curator"),
        ("Лидер сообщества", "community_leader"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"admin:user:setstatus:{user_id}:{value}",
                )
            ]
            for label, value in options
        ]
        + [
            [
                InlineKeyboardButton(
                    text="← Назад", callback_data=f"admin:user:{user_id}"
                )
            ]
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


def event_management_keyboard(event_id: int, status: str) -> InlineKeyboardMarkup:
    rows = []
    if status not in {"draft", "pending_approval", "cancelled"}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Участники и посещение",
                    callback_data=f"admin:event:participants:{event_id}",
                )
            ]
        )
    if status in {"approved", "published"}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Открыть регистрацию",
                    callback_data=f"admin:event:status:registration_open:{event_id}",
                )
            ]
        )
    elif status == "registration_open":
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="Закрыть регистрацию",
                        callback_data=f"admin:event:status:registration_closed:{event_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Мероприятие началось",
                        callback_data=f"admin:event:status:active:{event_id}",
                    )
                ],
            ]
        )
    elif status == "registration_closed":
        rows.append(
            [
                InlineKeyboardButton(
                    text="Мероприятие началось",
                    callback_data=f"admin:event:status:active:{event_id}",
                )
            ]
        )
    elif status == "active":
        rows.append(
            [
                InlineKeyboardButton(
                    text="Завершить мероприятие",
                    callback_data=f"admin:event:status:completed:{event_id}",
                )
            ]
        )
    elif status == "completed":
        rows.append(
            [
                InlineKeyboardButton(
                    text="Добавить активность после события",
                    callback_data=f"admin:activity:event:{event_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="← Назад", callback_data="admin:menu:activity")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def project_review_actions(project_id: int, stage: str) -> InlineKeyboardMarkup:
    if stage == "venue_review":
        rows = [
            [
                InlineKeyboardButton(
                    text="Одобрить площадку",
                    callback_data=f"admin:project:review:venue_approve:{project_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Напомнить позже",
                    callback_data=f"admin:project:snooze:{project_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Перенести проект",
                    callback_data=f"admin:project:review:postpone:{project_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"admin:project:review:reject:{project_id}",
                )
            ],
        ]
    else:
        rows = [
            [
                InlineKeyboardButton(
                    text="Взять на рассмотрение",
                    callback_data=f"admin:project:review:initial_accept:{project_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Вернуть на доработку",
                    callback_data=f"admin:project:review:revise:{project_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"admin:project:review:reject:{project_id}",
                )
            ],
        ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="admin:projects")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def project_snooze_keyboard(project_id: int) -> InlineKeyboardMarkup:
    options = (
        ("Через 1 день", 1),
        ("Через 2 дня", 2),
        ("Через 3 дня", 3),
        ("Через неделю", 7),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"admin:project:snooze_set:{project_id}:{days}",
                )
            ]
            for label, days in options
        ]
        + [[InlineKeyboardButton(text="Отмена", callback_data="admin:projects")]]
    )
