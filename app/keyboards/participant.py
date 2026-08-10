from collections.abc import Iterable

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.utils.deep_links import miniapp_events_url, miniapp_opportunities_url, miniapp_tasks_url


def main_menu(
    channel_url: str,
    privileged: bool = False,
    admin: bool = False,
    miniapp_url: str = "",
) -> ReplyKeyboardMarkup:
    """PR 36 (Bot/Mini App role split): the bot is a gateway now, not a
    second parallel interface. The old "👤 Личный кабинет"/"⚙️ Панель"
    entry points into the bot's own multi-screen menu trees
    (app/handlers/participant/cabinet.py, app/handlers/admin/panel.py) are
    deliberately no longer advertised here — the Mini App fully covers
    both (profile/portfolio/points/projects, and Admin/Leader Mode), and
    🔥 Открыть ЭРА already routes an admin/leader straight into their
    correct Mini App mode (see frontend/src/app/App.tsx's
    is_admin/is_leader branches). That old code is intentionally left in
    place, not deleted — see docs/BOT_VS_MINIAPP_AUDIT.md — in case the
    Mini App is temporarily unavailable and a fallback is needed; it's
    just no longer the advertised default UX.
    """
    del channel_url
    rows: list[list[KeyboardButton]] = []
    if miniapp_url:
        rows.append(
            [KeyboardButton(text="🔥 Открыть ЭРА", web_app=WebAppInfo(url=miniapp_url))]
        )
        rows.append(
            [
                KeyboardButton(
                    text="📅 Ближайшее", web_app=WebAppInfo(url=miniapp_events_url(miniapp_url))
                ),
                KeyboardButton(
                    text="✅ Мои задачи", web_app=WebAppInfo(url=miniapp_tasks_url(miniapp_url))
                ),
            ]
        )
        rows.append(
            [
                KeyboardButton(
                    text="⭐ Возможности",
                    web_app=WebAppInfo(url=miniapp_opportunities_url(miniapp_url)),
                )
            ]
        )
    else:
        # Mini App isn't configured, or is the "резервный сценарий" fallback
        # for when it's temporarily unavailable — fall back to the bot's
        # own inline menus (including the admin panel) rather than showing
        # broken WebApp buttons or leaving admins with no way in at all.
        rows.append([KeyboardButton(text="👤 Личный кабинет"), KeyboardButton(text="📅 Афиша")])
        rows.append([KeyboardButton(text="✅ Задачи"), KeyboardButton(text="⭐ Возможности")])
        if privileged or admin:
            rows.append([KeyboardButton(text="⚙️ Панель")])
    rows.append([KeyboardButton(text="💬 Связь")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите раздел ЭРА",
    )


def main_inline_keyboard(
    privileged: bool = False, admin: bool = False, miniapp_url: str = ""
) -> InlineKeyboardMarkup:
    """Inline equivalent of main_menu() above, for contexts that answer
    with an inline keyboard instead of the persistent reply keyboard
    (e.g. "← Главное меню" back-buttons). Same PR 36 role-split rationale."""
    rows: list[list[InlineKeyboardButton]] = []
    if miniapp_url:
        rows.append(
            [InlineKeyboardButton(text="🔥 Открыть ЭРА", web_app=WebAppInfo(url=miniapp_url))]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="📅 Ближайшее", web_app=WebAppInfo(url=miniapp_events_url(miniapp_url))
                ),
                InlineKeyboardButton(
                    text="✅ Мои задачи", web_app=WebAppInfo(url=miniapp_tasks_url(miniapp_url))
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="⭐ Возможности",
                    web_app=WebAppInfo(url=miniapp_opportunities_url(miniapp_url)),
                )
            ]
        )
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
    """A single WebApp button, used on admin notifications that used to
    carry admin: callback buttons (approve/reject/etc.) — that review now
    happens in the Mini App, not in a bot chat flow. Returns None (send no
    keyboard) rather than a broken one if the Mini App isn't configured,
    mirroring the `if miniapp_url:` guard already used in main_menu() and
    main_inline_keyboard() above."""
    if not miniapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=miniapp_url))]]
    )


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
    internal_chat_url: str | None = None,
    external_chat_url: str | None = None,
) -> InlineKeyboardMarkup:
    del internal_chat_url, external_chat_url
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Мои данные", callback_data="cabinet:profile")],
            [InlineKeyboardButton(text="✅ Задачи", callback_data="cabinet:tasks")],
            [InlineKeyboardButton(text="🎓 Портфолио", callback_data="cabinet:portfolio")],
            [InlineKeyboardButton(text="🏆 Баллы", callback_data="cabinet:points_hub")],
            [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
        ]
    )


def points_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Баланс и история", callback_data="cabinet:points")],
            [InlineKeyboardButton(text="🏅 Достижения и знаки", callback_data="cabinet:achievements")],
            [InlineKeyboardButton(text="🏆 Рейтинг", callback_data="cabinet:rating")],
            [InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")],
        ]
    )


def profile_sections_keyboard(
    internal_chat_url: str | None = None,
    external_chat_url: str | None = None,
) -> InlineKeyboardMarkup:
    del internal_chat_url, external_chat_url
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить данные", callback_data="profile:settings")],
            [InlineKeyboardButton(text="📅 Мероприятия", callback_data="cabinet:events")],
            [InlineKeyboardButton(text="💡 Проекты", callback_data="cabinet:projects")],
            [
                InlineKeyboardButton(text="🎓 Портфолио", callback_data="cabinet:portfolio"),
                InlineKeyboardButton(text="📄 Скачать PDF", callback_data="portfolio:resume"),
            ],
            [InlineKeyboardButton(text="🧩 Направления", callback_data="cabinet:departments")],
            [InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")],
        ]
    )


def profile_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Имя", callback_data="profile:edit:first_name"),
                InlineKeyboardButton(text="Фамилия", callback_data="profile:edit:last_name"),
            ],
            [
                InlineKeyboardButton(text="Дата рождения", callback_data="profile:birth_date"),
                InlineKeyboardButton(text="Телефон", callback_data="profile:phone"),
            ],
            [
                InlineKeyboardButton(text="Email", callback_data="profile:email"),
                InlineKeyboardButton(text="Город", callback_data="profile:edit:city"),
            ],
            [InlineKeyboardButton(text="Учёба / работа", callback_data="profile:edit:education_work")],
            [InlineKeyboardButton(text="Занятость", callback_data="profile:edit:occupation")],
            [InlineKeyboardButton(text="Фото", callback_data="profile:photo")],
            [InlineKeyboardButton(text="Соцсети", callback_data="profile:socials")],
            [InlineKeyboardButton(text="← Мои данные", callback_data="cabinet:profile")],
        ]
    )


def cabinet_keyboard() -> InlineKeyboardMarkup:
    return journey_keyboard()


def event_list_keyboard(events: Iterable) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=event.title[:50], callback_data=f"event:view:{event.id}")] for event in events]
    rows.append([InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_card_keyboard(event_id: int, can_register: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if can_register:
        rows.append([InlineKeyboardButton(text="Зарегистрироваться", callback_data=f"event:join:{event_id}")])
    rows.append([InlineKeyboardButton(text="← Афиша", callback_data="events:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def project_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💡 Создать проект", callback_data="project:new:guided")],
            [InlineKeyboardButton(text="📁 Мои проекты", callback_data="cabinet:projects")],
            [InlineKeyboardButton(text="📝 Черновики", callback_data="projects:drafts")],
            [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
        ]
    )


def project_result_keyboard(project_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отправить на рассмотрение", callback_data=f"project:submit:{project_id}")],
            [InlineKeyboardButton(text="Изменить ответы", callback_data=f"project:resume:{project_id}")],
            [InlineKeyboardButton(text="Сохранить как черновик", callback_data=f"project:pause:{project_id}")],
            [InlineKeyboardButton(text="← К проектам", callback_data="projects:menu")],
        ]
    )


def project_question_keyboard(index: int, has_hint: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_hint:
        rows.append([InlineKeyboardButton(text="✨ Получить подсказку", callback_data=f"project:hint:{index}")])
    rows.append([InlineKeyboardButton(text="Сохранить и выйти", callback_data="project:pause")])
    if index > 0:
        rows.append([InlineKeyboardButton(text="← Предыдущий вопрос", callback_data="project:previous")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def project_drafts_keyboard(projects: Iterable) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"Продолжить: {project.title[:35]}", callback_data=f"project:resume:{project.id}")] for project in projects]
    rows.append([InlineKeyboardButton(text="← К проектам", callback_data="projects:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def departments_keyboard(general_chat_url: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🌿 Внутренние связи", callback_data="department:view:internal")],
        [InlineKeyboardButton(text="🌍 Внешние связи", callback_data="department:view:external")],
        [InlineKeyboardButton(text="👥 Кто отвечает за направления", callback_data="team:offices")],
    ]
    if general_chat_url:
        rows.append([InlineKeyboardButton(text="💬 Общий чат ЭРА", url=general_chat_url)])
    rows.append([InlineKeyboardButton(text="← Связь", callback_data="contact:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def department_keyboard(chat_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Присоединиться к чату", url=chat_url)],
            [InlineKeyboardButton(text="← Команда ЭРА", callback_data="team:menu")],
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
        [InlineKeyboardButton(text=f"🔨 {auction.title}", callback_data=f"auction:view:{auction.id}")]
        for auction in auctions
    )
    rows.append([InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def portfolio_keyboard(items: Iterable = ()) -> InlineKeyboardMarkup:
    del items
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👁 Что войдёт в портфолио", callback_data="portfolio:view")],
            [InlineKeyboardButton(text="📎 Добавить достижение", callback_data="portfolio:upload")],
            [InlineKeyboardButton(text="📄 Скачать портфолио PDF", callback_data="portfolio:resume")],
            [InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")],
        ]
    )


def tasks_keyboard(tasks: Iterable, joined_ids: set[int]) -> InlineKeyboardMarkup:
    rows = []
    for task in tasks:
        if task.id in joined_ids:
            callback = f"task:view:{task.id}"
            label = f"✅ {task.title[:38]}"
        else:
            callback = f"task:join:{task.id}"
            label = f"🙌 Хочу помочь: {task.title[:28]}"
        rows.append([InlineKeyboardButton(text=label, callback_data=callback)])
    rows.append([InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
