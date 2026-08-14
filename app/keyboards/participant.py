from collections.abc import Iterable

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)

from app.utils.deep_links import (
    miniapp_events_url,
    miniapp_opportunities_url,
    miniapp_profile_url,
    miniapp_tasks_url,
)


def main_inline_keyboard(
    privileged: bool = False, admin: bool = False, miniapp_url: str = ""
) -> InlineKeyboardMarkup:
    """The bot's one and only "main menu" surface. Used everywhere the bot
    used to send a persistent ReplyKeyboardMarkup main menu (/start,
    registration/role-change approvals, "← Главное меню" back-buttons) —
    that keyboard is gone (see
    app/middlewares/legacy_keyboard_cleanup.py for the one-time
    ReplyKeyboardRemove migration for users who already have it cached).
    PR 36 (Bot/Mini App role split): when miniapp_url is configured,
    🔥 Открыть ЭРА is the primary action; the old "👤 Личный
    кабинет"/"⚙️ Панель" bot-side menu tree only appears as a fallback for
    when the Mini App isn't configured (e.g. local dev) — see
    docs/BOT_VS_MINIAPP_AUDIT.md.

    2026-08 redesign brief section 36 ("бот не должен дублировать
    приложение"): the three separate quick-access buttons this used to
    carry (📅 Ближайшее / ✅ Мои задачи / ⭐ Возможности, each a direct
    WebApp deep link) collapsed into one 🧭 Навигация button — a bot
    message that explains what's in the app and links out to it, rather
    than the bot itself trying to be a second, parallel set of shortcuts
    into the same screens. See navigation_guide_keyboard() and
    app/handlers/participant/navigation.py's nav_guide_callback for what
    that button opens."""
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
    """A single WebApp button, used on admin notifications that used to
    carry admin: callback buttons (approve/reject/etc.) — that review now
    happens in the Mini App, not in a bot chat flow. Returns None (send no
    keyboard) rather than a broken one if the Mini App isn't configured,
    mirroring the `if miniapp_url:` guard already used in
    main_inline_keyboard() above."""
    if not miniapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=miniapp_url))]]
    )


def navigation_guide_keyboard(
    miniapp_url: str, admin: bool = False, privileged: bool = False
) -> InlineKeyboardMarkup:
    """Buttons under the "🧭 Навигация" bot message (2026-08 redesign
    brief section 36) — direct WebApp deep links into the four screens the
    message text describes, plus one extra row into the admin/leader
    workspace when the user actually has one. Every button here just
    opens the Mini App at a specific screen; none of them re-implement
    that screen's content in the bot."""
    rows = [
        [
            InlineKeyboardButton(
                text="📅 Мероприятия", web_app=WebAppInfo(url=miniapp_events_url(miniapp_url))
            ),
            InlineKeyboardButton(
                text="✅ Задачи", web_app=WebAppInfo(url=miniapp_tasks_url(miniapp_url))
            ),
        ],
        [
            InlineKeyboardButton(
                text="⭐ Возможности",
                web_app=WebAppInfo(url=miniapp_opportunities_url(miniapp_url)),
            ),
            InlineKeyboardButton(
                text="👤 Профиль", web_app=WebAppInfo(url=miniapp_profile_url(miniapp_url))
            ),
        ],
    ]
    if admin:
        rows.append(
            [InlineKeyboardButton(text="⚙️ Режим администратора", web_app=WebAppInfo(url=miniapp_url))]
        )
    elif privileged:
        rows.append(
            [InlineKeyboardButton(text="🧭 Режим лидера", web_app=WebAppInfo(url=miniapp_url))]
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
