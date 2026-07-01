from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.keyboards.admin import admin_panel_keyboard
from app.keyboards.leader import leader_panel_keyboard
from app.keyboards.participant import (
    contact_keyboard,
    event_list_keyboard,
    journey_keyboard,
    main_inline_keyboard,
    team_keyboard,
)
from app.repositories.users import rating, user_stats
from app.services.event_service import published_events
from app.services.points_service import total_points
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role

router = Router(name="participant_navigation")

LEADER_PANEL_TEXT = """Панель лидера

Здесь лидер не просто смотрит разделы, а двигает команду: назначает задачи, публикует открытые задачи, ищет помощников, предлагает мероприятия, поощрения, повышения и знаки.

Лидер в ЭРА — это ответственность за людей, движение и результат."""


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


def _has_admin_access(user: User | None) -> bool:
    if not user:
        return False
    if user.role == Role.ADMIN:
        return True
    return any(
        grant.is_active for grant in (getattr(user, "permission_grants", None) or [])
    )


async def _send_main_menu(message: Message, user: User | None) -> None:
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(
        "Главное меню ЭРА",
        reply_markup=main_inline_keyboard(
            privileged=user.role in PRIVILEGED_ROLES,
            admin=_has_admin_access(user),
        ),
    )


async def _send_personal_cabinet(
    message: Message,
    user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    stats = await user_stats(session, user.id)
    rows = await rating(session, limit=1000)
    place = next(
        (index for index, (item, _) in enumerate(rows, 1) if item.id == user.id), "—"
    )
    await message.answer(
        texts.journey_text(user, stats, place),
        reply_markup=journey_keyboard(
            settings.internal_department_chat_url,
            settings.external_department_chat_url,
        ),
    )


async def _send_event_list(
    message: Message, user: User | None, session: AsyncSession
) -> None:
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    events = await published_events(session)
    if not events:
        await message.answer(texts.EVENTS_EMPTY)
        return
    await message.answer(
        "Афиша ЭРА 📅\n\nВыберите мероприятие, чтобы увидеть программу, место, баллы и свободные места",
        reply_markup=event_list_keyboard(events),
    )


@router.message(F.text == "👤 Личный кабинет")
async def personal_cabinet_button(
    message: Message,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await _send_personal_cabinet(message, user, session, settings)


@router.message(F.text == "📅 Афиша")
async def schedule_button(
    message: Message, user: User | None, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await _send_event_list(message, user, session)


@router.message(F.text == "⭐ Возможности")
async def opportunities_button(
    message: Message, user: User | None, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    balance = await total_points(session, user.id)
    await message.answer(
        f"⭐ Возможности\n\nВаш баланс: {balance} баллов\n\n"
        "Здесь доступны каталог возможностей, аукционы, награды и специальные форматы ЭРА.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Открыть возможности", callback_data="rewards:menu")],
                [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
            ]
        ),
    )


@router.message(F.text == "💬 Связь")
async def contact_button(
    message: Message, user: User | None, state: FSMContext
) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(
        "💬 Связь\n\nЗдесь можно задать вопрос, найти команду ЭРА, открыть правила или информацию о боте.",
        reply_markup=contact_keyboard(),
    )


@router.callback_query(F.data == "contact:menu")
async def contact_callback(call: CallbackQuery, user: User | None) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await call.message.answer("💬 Связь\n\nВыберите, что Вам нужно.", reply_markup=contact_keyboard())


@router.callback_query(F.data == "team:menu")
async def team_callback(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await call.message.answer(
        "👥 Команда ЭРА\n\nДепартаменты, контакты, руководители направлений и чаты.",
        reply_markup=team_keyboard(settings.general_chat_url),
    )


@router.callback_query(F.data == "rules:open")
async def rules_callback(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(texts.CHAT_RULES, reply_markup=contact_keyboard())


@router.message(F.text == "⚙️ Панель")
async def panel_button(message: Message, user: User | None, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.NO_ACCESS)
        return
    if _has_admin_access(user):
        await message.answer(texts.ADMIN_PANEL, reply_markup=admin_panel_keyboard())
        return
    if user.role in PRIVILEGED_ROLES:
        await message.answer(LEADER_PANEL_TEXT, reply_markup=leader_panel_keyboard())
        return
    await message.answer(texts.NO_ACCESS)


@router.callback_query(F.data == "panel:open")
async def panel_callback(call: CallbackQuery, user: User | None) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.NO_ACCESS)
        return
    if _has_admin_access(user):
        await call.message.answer(texts.ADMIN_PANEL, reply_markup=admin_panel_keyboard())
        return
    if user.role in PRIVILEGED_ROLES:
        await call.message.answer(LEADER_PANEL_TEXT, reply_markup=leader_panel_keyboard())
        return
    await call.message.answer(texts.NO_ACCESS)


@router.message(F.text == "🧭 Главное меню")
async def main_menu_message(message: Message, user: User | None, state: FSMContext) -> None:
    await state.clear()
    await _send_main_menu(message, user)
