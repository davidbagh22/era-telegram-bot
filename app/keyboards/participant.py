from collections.abc import Iterable

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu(
    channel_url: str,
    privileged: bool = False,
    admin: bool = False,
) -> ReplyKeyboardMarkup:
    del channel_url
    rows = [
        [KeyboardButton(text="🌱 Мой путь"), KeyboardButton(text="📅 Мероприятия")],
        [KeyboardButton(text="💡 Проекты"), KeyboardButton(text="🏆 Рейтинг")],
        [
            KeyboardButton(text="🤝 Команда ЭРА"),
            KeyboardButton(text="💬 Задать вопрос"),
        ],
        [KeyboardButton(text="ℹ️ О боте")],
    ]
    if privileged:
        rows.append([KeyboardButton(text="🧭 Панель лидера")])
    if admin:
        rows.append([KeyboardButton(text="⚙️ Управление")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите раздел ЭРА",
    )


def about_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌱 Мой путь", callback_data="cabinet:open"),
                InlineKeyboardButton(
                    text="📅 Мероприятия", callback_data="events:list"
                ),
            ],
            [
                InlineKeyboardButton(text="💡 Проекты", callback_data="projects:menu"),
                InlineKeyboardButton(
                    text="🤝 Команда", callback_data="departments:menu"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎁 Баллы и возможности", callback_data="rewards:menu"
                )
            ],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]
    )


def journey_keyboard(
    internal_chat_url: str | None = None,
    external_chat_url: str | None = None,
) -> InlineKeyboardMarkup:
    chat_row = []
    if internal_chat_url:
        chat_row.append(
            InlineKeyboardButton(text="Внутренние связи", url=internal_chat_url)
        )
    if external_chat_url:
        chat_row.append(
            InlineKeyboardButton(text="Внешние связи", url=external_chat_url)
        )
    rows = [
        [
            InlineKeyboardButton(
                text="🎓 Портфолио", callback_data="cabinet:portfolio"
            ),
            InlineKeyboardButton(
                text="🎟 Мои мероприятия", callback_data="cabinet:events"
            ),
        ],
        [
            InlineKeyboardButton(
                text="💡 Мои проекты", callback_data="cabinet:projects"
            ),
            InlineKeyboardButton(text="✅ Мои задания", callback_data="cabinet:tasks"),
        ],
        [
            InlineKeyboardButton(
                text="🎁 Награды и аукционы", callback_data="rewards:menu"
            )
        ],
    ]
    if chat_row:
        rows.append(chat_row)
    rows.append(
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cabinet_keyboard() -> InlineKeyboardMarkup:
    return journey_keyboard()


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
                    text="✨ Создать проект пошагово",
                    callback_data="project:new:guided",
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
                    text="Изменить ответы",
                    callback_data=f"project:resume:{project_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Сохранить как черновик",
                    callback_data=f"project:pause:{project_id}",
                )
            ],
            [InlineKeyboardButton(text="← К проектам", callback_data="projects:menu")],
        ]
    )


def project_question_keyboard(index: int, has_hint: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_hint:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✨ ИИ-подсказка", callback_data=f"project:hint:{index}"
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="Сохранить и выйти", callback_data="project:pause")]
    )
    if index > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    text="← Предыдущий вопрос", callback_data="project:previous"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def project_drafts_keyboard(projects: Iterable) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"Продолжить: {project.title[:35]}",
                callback_data=f"project:resume:{project.id}",
            )
        ]
        for project in projects
    ]
    rows.append(
        [InlineKeyboardButton(text="← К проектам", callback_data="projects:menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def departments_keyboard(general_chat_url: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="🌿 Внутренние связи", callback_data="department:view:internal"
            )
        ],
        [
            InlineKeyboardButton(
                text="🌍 Внешние связи", callback_data="department:view:external"
            )
        ],
        [
            InlineKeyboardButton(
                text="👥 Кто отвечает за направления", callback_data="team:offices"
            )
        ],
    ]
    if general_chat_url:
        rows.append(
            [InlineKeyboardButton(text="💬 Общий чат ЭРА", url=general_chat_url)]
        )
    rows.append(
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def department_keyboard(chat_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Присоединиться к чату", url=chat_url)],
            [InlineKeyboardButton(text="← Назад", callback_data="departments:menu")],
        ]
    )


def rewards_keyboard(rewards: Iterable, auctions: Iterable) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🎁 {reward.name} · {reward.point_cost} баллов",
                callback_data=f"reward:view:{reward.id}",
            )
        ]
        for reward in rewards
    ]
    rows.extend(
        [
            InlineKeyboardButton(
                text=f"🔨 {auction.title}", callback_data=f"auction:view:{auction.id}"
            )
        ]
        for auction in auctions
    )
    rows.append([InlineKeyboardButton(text="← Мой путь", callback_data="cabinet:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def portfolio_keyboard(items: Iterable = ()) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="📎 Добавить достижение", callback_data="portfolio:upload"
            )
        ],
        [
            InlineKeyboardButton(
                text="📄 Скачать резюме ЭРА", callback_data="portfolio:resume"
            )
        ],
    ]
    rows.extend(
        [
            InlineKeyboardButton(
                text=f"Скачать: {item.title[:32]}",
                callback_data=f"portfolio:file:{item.id}",
            )
        ]
        for item in items
        if item.file_id and item.status == "verified"
    )
    rows.append([InlineKeyboardButton(text="← Мой путь", callback_data="cabinet:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tasks_keyboard(tasks: Iterable, joined_ids: set[int]) -> InlineKeyboardMarkup:
    rows = []
    for task in tasks:
        if task.id in joined_ids:
            callback = f"task:view:{task.id}"
            label = f"✅ {task.title[:38]}"
        else:
            callback = f"task:join:{task.id}"
            label = f"🙌 Присоединиться: {task.title[:28]}"
        rows.append([InlineKeyboardButton(text=label, callback_data=callback)])
    rows.append([InlineKeyboardButton(text="← Мой путь", callback_data="cabinet:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
