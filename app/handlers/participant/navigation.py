from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.keyboards.bot_shell import (
    contact_keyboard,
    has_leaders_entry,
    main_reply_keyboard,
    navigation_guide_keyboard,
    team_keyboard,
)
from app.keyboards.participant import (
    event_list_keyboard,
    journey_keyboard,
    open_app_button,
    opportunities_hub_keyboard,
)
from app.repositories.users import rating, user_stats
from app.services import anniversary_registration_service as anniversary
from app.services.event_service import published_events
from app.services.points_service import total_points
from app.services.feature_flags import Feature, feature_enabled
from app.utils import texts, ux_texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role, STATUS_LABELS
from app.utils.deep_links import miniapp_admin_url, miniapp_leader_url

router = Router(name="participant_navigation")

LEADER_PANEL_TEXT = """Панель лидера

Задачи, помощники, мероприятия, поощрения и знаки — здесь. Лидер отвечает за людей и результат."""

NAVIGATION_PARTICIPANT = """🧭 <b>Навигация по ЭРА</b>

Работа в приложении. Выберите действие:

🧭 <b>Мой вектор</b> — короткая отметка в Telegram
💡 <b>Проекты</b> — идея и ведение
📅 <b>События</b> — афиша и регистрация
✅ <b>Мои задачи</b> — включиться в работу
⭐ <b>Возможности</b> — предложения и награды
👥 <b>Сообщество</b> — рейтинг и активность
👤 <b>Профиль</b> — путь, баллы, портфолио

Нужен человек — «💬 Связь»."""

NAVIGATION_LEADER = NAVIGATION_PARTICIPANT + """

🧭 <b>Режим лидера</b> — команда, задачи и решения по направлению."""

NAVIGATION_ADMIN = NAVIGATION_PARTICIPANT + """

⚙️ <b>Режим администратора</b> — заявки, проекты, мероприятия, задания, коммуникации и аналитика."""

CONTACT_TEXT = """💬 <b>Связь с ЭРА</b>

Один вход: вопрос, человек или чат.

❓ вопрос — команде ЭРА
👥 люди — кто за что отвечает
🏛 структура и чаты — рядом ниже

Выберите, что нужно сейчас."""

TEAM_TEXT = """👥 <b>Команда ЭРА</b>

Кто за направление и куда писать — «К кому обратиться». Чаты и департаменты рядом."""


def _approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


def _has_admin_access(user: User | None) -> bool:
    if not user:
        return False
    if user.role == Role.ADMIN:
        return True
    return any(grant.is_active for grant in (getattr(user, "permission_grants", None) or []))


def _cabinet_text(user: User, stats: dict[str, int], place: int | str) -> str:
    status = STATUS_LABELS.get(user.participation_status, user.participation_status)
    return ux_texts.cabinet_home_text(user.first_name, status, stats["points"], place)


async def _send_main_menu(
    message: Message, user: User | None, settings: Settings | None = None, *, session: AsyncSession | None = None,
) -> None:
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    from app.services.media_leadership_service import is_media_chair
    featured = session is not None and await anniversary.menu_available(session)
    anniversary_registered = bool(
        featured and session is not None and user is not None
        and await anniversary.user_already_registered(session, user.telegram_id, user)
    )
    if featured and anniversary_registered:
        menu_text = f"{ux_texts.MAIN_INLINE_MENU}\n\n{anniversary.MENU_REGISTERED_SHORTCUT}"
    elif featured:
        menu_text = f"{ux_texts.MAIN_INLINE_MENU}\n\n{anniversary.MENU_SHORTCUT}"
    else:
        menu_text = ux_texts.MAIN_INLINE_MENU
    await message.answer(
        menu_text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_reply_keyboard(
            leaders=has_leaders_entry(user),
            miniapp_url=settings.effective_miniapp_url if settings else "",
            admin=user.role == Role.ADMIN or bool(settings and getattr(user, 'telegram_id', None) in getattr(settings, 'admin_ids', [])),
            media_chair=bool(settings and is_media_chair(user, settings)),
            anniversary=featured,
            anniversary_registered=anniversary_registered,
        ),
    )


async def _send_personal_cabinet(message: Message, user: User, session: AsyncSession, settings: Settings) -> None:
    stats = await user_stats(session, user.id)
    rows = await rating(session, limit=1000)
    place = next((index for index, (item, _) in enumerate(rows, 1) if item.id == user.id), "—")
    await message.answer(
        _cabinet_text(user, stats, place),
        reply_markup=journey_keyboard(settings.internal_department_chat_url, settings.external_department_chat_url),
    )


async def _send_event_list(message: Message, user: User | None, session: AsyncSession) -> None:
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    events = await published_events(session)
    if not events:
        await message.answer(ux_texts.EVENTS_EMPTY)
        return
    await message.answer(ux_texts.EVENTS_LIST_HEADER, reply_markup=event_list_keyboard(events))


@router.message(F.text == "👤 Личный кабинет")
async def personal_cabinet_button(message: Message, user: User | None, session: AsyncSession, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await _send_personal_cabinet(message, user, session, settings)


@router.message(F.text == "📅 Афиша")
async def schedule_button(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await _send_event_list(message, user, session)


@router.message(F.text == "⭐ Возможности")
async def opportunities_button(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    balance = await total_points(session, user.id)
    await message.answer(
        f"⭐ Возможности\n\nБаланс: {balance} баллов.\n"
        "Предложения, аукцион и каталог за баллы — ниже.",
        reply_markup=opportunities_hub_keyboard(),
    )


@router.message(F.text == "💬 Связь")
async def contact_button(message: Message, user: User | None, state: FSMContext, settings: Settings | None = None) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(CONTACT_TEXT, parse_mode=ParseMode.HTML, reply_markup=contact_keyboard(
        support_threads=bool(settings and feature_enabled(settings, Feature.SUPPORT_THREADS, user.telegram_id))))


async def _send_navigation_guide(message: Message, user: User | None, settings: Settings) -> None:
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    is_admin = _has_admin_access(user)
    is_privileged = user.role in PRIVILEGED_ROLES
    if is_admin:
        text = NAVIGATION_ADMIN
    elif is_privileged:
        text = NAVIGATION_LEADER
    else:
        text = NAVIGATION_PARTICIPANT
    await message.answer(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=navigation_guide_keyboard(
            settings.effective_miniapp_url,
            admin=is_admin,
            privileged=is_privileged,
        ),
    )


@router.callback_query(F.data == "nav:guide")
async def nav_guide_callback(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    await call.answer()
    await _send_navigation_guide(call.message, user, settings)


@router.message(F.text == "🧭 Навигация", F.chat.type == "private")
@router.message(Command("navigation"), F.chat.type == "private")
async def navigation_command(message: Message, user: User | None, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    await _send_navigation_guide(message, user, settings)


@router.callback_query(F.data == "contact:menu")
async def contact_callback(call: CallbackQuery, user: User | None, state: FSMContext, faq_context: dict | None = None, settings: Settings | None = None) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await state.clear()
    if faq_context:
        await state.update_data(faq_context=faq_context)
    await call.message.answer(CONTACT_TEXT, parse_mode=ParseMode.HTML, reply_markup=contact_keyboard(
        faq_context["back"] if faq_context else None,
        support_threads=bool(settings and feature_enabled(settings, Feature.SUPPORT_THREADS, user.telegram_id))))


@router.callback_query(F.data == "team:menu")
async def team_callback(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await call.message.answer(
        TEAM_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=team_keyboard(settings.general_chat_url),
    )


@router.callback_query(F.data == "rules:open")
async def rules_callback(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(texts.CHAT_RULES, reply_markup=contact_keyboard())


@router.message(F.text == "⚙️ Панель")
async def panel_button(message: Message, user: User | None, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.NO_ACCESS)
        return
    if _has_admin_access(user):
        await message.answer(texts.ADMIN_PANEL_MOVED, reply_markup=open_app_button(miniapp_admin_url(settings.effective_miniapp_url)))
        return
    if user.role in PRIVILEGED_ROLES:
        await message.answer(texts.LEADER_PANEL_MOVED, reply_markup=open_app_button(miniapp_leader_url(settings.effective_miniapp_url)))
        return
    await message.answer(texts.NO_ACCESS)


@router.callback_query(F.data == "panel:open")
async def panel_callback(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.NO_ACCESS)
        return
    if _has_admin_access(user):
        await call.message.answer(texts.ADMIN_PANEL_MOVED, reply_markup=open_app_button(miniapp_admin_url(settings.effective_miniapp_url)))
        return
    if user.role in PRIVILEGED_ROLES:
        await call.message.answer(texts.LEADER_PANEL_MOVED, reply_markup=open_app_button(miniapp_leader_url(settings.effective_miniapp_url)))
        return
    await call.message.answer(texts.NO_ACCESS)


@router.message(F.text == "🧭 Главное меню")
async def main_menu_message(
    message: Message, user: User | None, state: FSMContext, settings: Settings, session: AsyncSession | None = None,
) -> None:
    await state.clear()
    await _send_main_menu(message, user, settings, session=session)
