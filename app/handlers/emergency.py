from aiogram import F, Bot, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.handlers.participant.navigation import (
    LEADER_PANEL_TEXT,
    _has_admin_access,
    _send_event_list,
    _send_main_menu,
    _send_personal_cabinet,
)
from app.keyboards.admin import admin_panel_keyboard
from app.keyboards.common import registration_keyboard, subscription_keyboard
from app.keyboards.leader import leader_panel_keyboard
from app.keyboards.participant import contact_keyboard, project_menu_keyboard
from app.services.points_service import total_points
from app.services.subscription_service import SubscriptionCheckError, is_channel_member
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES

router = Router(name="emergency")
MENU_BUTTONS = {"👤 Личный кабинет", "📅 Афиша", "💡 Проекты", "⭐ Возможности", "💬 Связь", "⚙️ Панель", "🧭 Главное меню"}


def _approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


async def _subscription_ok(bot: Bot, telegram_id: int, settings: Settings) -> bool | None:
    try:
        return await is_channel_member(bot, telegram_id, settings)
    except SubscriptionCheckError:
        return None


@router.message(StateFilter("*"), CommandStart(), F.chat.type == "private")
@router.message(StateFilter("*"), Command("menu"), F.chat.type == "private")
async def rescue_start(message: Message, bot: Bot, user: User | None, settings: Settings, state: FSMContext) -> None:
    await state.clear()
    subscribed = await _subscription_ok(bot, message.from_user.id, settings)
    if subscribed is False:
        await message.answer(
            texts.SUBSCRIPTION_REQUIRED,
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if subscribed is None and not _approved(user):
        await message.answer(
            getattr(
                texts,
                "SUBSCRIPTION_CHECK_UNAVAILABLE",
                "Проверка подписки временно недоступна. Попробуйте ещё раз немного позже.",
            ),
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if user is None:
        await message.answer(texts.WELCOME, reply_markup=registration_keyboard())
        return
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await _send_main_menu(message, user)


@router.message(StateFilter("*"), F.text.in_(MENU_BUTTONS), F.chat.type == "private")
async def rescue_menu_button(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    text = message.text or ""
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    if text == "👤 Личный кабинет":
        await _send_personal_cabinet(message, user, session, settings)
        return
    if text == "📅 Афиша":
        await _send_event_list(message, user, session)
        return
    if text == "💡 Проекты":
        await message.answer("💡 Проекты\n\nСоздавайте инициативы, дорабатывайте идеи и собирайте команду.", reply_markup=project_menu_keyboard())
        return
    if text == "⭐ Возможности":
        balance = await total_points(session, user.id)
        await message.answer(f"⭐ Возможности\n\nВаш баланс: {balance} баллов\n\nОткройте каталог возможностей через меню.")
        return
    if text == "💬 Связь":
        await message.answer("💬 Связь\n\nВыберите, что Вам нужно.", reply_markup=contact_keyboard())
        return
    if text == "⚙️ Панель":
        if _has_admin_access(user):
            await message.answer(texts.ADMIN_PANEL, reply_markup=admin_panel_keyboard())
            return
        if user.role in PRIVILEGED_ROLES:
            await message.answer(LEADER_PANEL_TEXT, reply_markup=leader_panel_keyboard())
            return
        await message.answer(texts.NO_ACCESS)
        return
    await _send_main_menu(message, user)
