from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(
    channel_url: str,
    privileged: bool = False,
    admin: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    rows.extend(
        [
            [InlineKeyboardButton(text="Мой кабинет", callback_data="cabinet:open")],
            [InlineKeyboardButton(text="Мероприятия", callback_data="events:list")],
            [
                InlineKeyboardButton(
                    text="Создать проект", callback_data="projects:menu"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Департаменты и направления", callback_data="departments:menu"
                )
            ],
            [InlineKeyboardButton(text="Перейти на канал ЭРА", url=channel_url)],
            [
                InlineKeyboardButton(
                    text="Задать вопрос", callback_data="question:start"
                )
            ],
        ]
    )
    if privileged:
        rows.append(
            [InlineKeyboardButton(text="Панель лидера", callback_data="leader:panel")]
        )
    if admin:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Панель администратора", callback_data="admin:panel"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cabinet_keyboard() -> InlineKeyboardMarkup:
    options = (
        ("Профиль", "cabinet:profile"),
        ("Мой путь в ЭРА", "cabinet:journey"),
        ("Баллы", "cabinet:points"),
        ("Рейтинг", "cabinet:rating"),
        ("Моё портфолио", "cabinet:portfolio"),
        ("Мои мероприятия", "cabinet:events"),
        ("Мои проекты", "cabinet:projects"),
        ("Мои задачи", "cabinet:tasks"),
        ("Мои департаменты", "cabinet:departments"),
        ("Главное меню", "menu:main"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=callback)]
            for label, callback in options
        ]
    )


def event_list_keyboard(events: Iterable) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=event.title[:50], callback_data=f"event:view:{event.id}"
            )
        ]
        for event in events
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_card_keyboard(event_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Зарегистрироваться", callback_data=f"event:join:{event_id}"
                )
            ],
            [InlineKeyboardButton(text="Назад", callback_data="events:list")],
        ]
    )


def project_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Создать проект с ИИ", callback_data="project:new:ai"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Создать проект вручную", callback_data="project:new:manual"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Мои проекты", callback_data="cabinet:projects"
                )
            ],
            [InlineKeyboardButton(text="Черновики", callback_data="projects:drafts")],
            [InlineKeyboardButton(text="Назад", callback_data="menu:main")],
        ]
    )


def project_result_keyboard(project_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отправить на рассмотрение",
                    callback_data=f"project:submit:{project_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Доработать с ИИ",
                    callback_data=f"project:improve:{project_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Сохранить черновик",
                    callback_data=f"project:save:{project_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Начать заново", callback_data="project:new:ai"
                )
            ],
        ]
    )


def departments_keyboard() -> InlineKeyboardMarkup:
    options = (
        ("Внутренние связи", "department:view:internal"),
        ("Внешние связи", "department:view:external"),
        ("Мои направления", "cabinet:departments"),
        ("Подать заявку", "department:apply:start"),
        ("Чаты департаментов", "department:chats"),
        ("Назад", "menu:main"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=callback)]
            for label, callback in options
        ]
    )


def department_keyboard(chat_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подать заявку", callback_data="department:apply:start"
                )
            ],
            [InlineKeyboardButton(text="Перейти в чат", url=chat_url)],
            [InlineKeyboardButton(text="Назад", callback_data="departments:menu")],
        ]
    )
