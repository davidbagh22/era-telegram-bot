from aiogram import F, Bot, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.keyboards.common import registration_keyboard, subscription_keyboard
from app.keyboards.participant import main_inline_keyboard
from app.keyboards.registration import pending_registration_keyboard
from app.services.subscription_service import SubscriptionCheckError, is_channel_member
from app.utils import texts, ux_texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role

router = Router(name="start")


async def show_home(message: Message, user: User, settings: Settings) -> None:
    if user.is_blocked or user.is_archived:
        await message.answer(texts.BLOCKED)
        return
    if user.application_status == ApplicationStatus.PENDING:
        await message.answer(
            texts.APPLICATION_PENDING,
            reply_markup=pending_registration_keyboard(settings.era_channel_url),
        )
        return
    if user.application_status == ApplicationStatus.REJECTED:
        await message.answer(texts.APPLICATION_REJECTED)
        return
    if user.application_status == ApplicationStatus.NEEDS_INFO:
        await message.answer(
            texts.APPLICATION_PENDING,
            reply_markup=pending_registration_keyboard(settings.era_channel_url),
        )
        return
    await message.answer(
        ux_texts.MAIN_MENU,
        reply_markup=main_inline_keyboard(
            privileged=user.role in PRIVILEGED_ROLES,
            admin=user.role == Role.ADMIN
            or any(
                grant.is_active
                for grant in (getattr(user, "permission_grants", None) or [])
            ),
            miniapp_url=settings.effective_miniapp_url,
        ),
    )


async def _subscription_ok(bot: Bot, telegram_id: int, settings: Settings) -> bool | None:
    try:
        return await is_channel_member(bot, telegram_id, settings)
    except SubscriptionCheckError:
        return None


def _approved_existing_user(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


# NOTE: start() below (and by extension show_home()'s CommandStart/"menu"
# call path) is unreachable in production. app/bot.py's create_dispatcher()
# includes emergency.router before this router, and emergency.rescue_start
# is registered on StateFilter("*") + the same CommandStart()/Command("menu")
# + F.chat.type == "private" filters -- aiogram first-match-wins routing
# means rescue_start always intercepts these updates first (see
# tests/test_fsm_global_recovery.py::test_emergency_router_is_first).
#
# The deep-link payload parsing that used to live here as
# _try_start_task_submission_from_deep_link() / _try_start_activity_
# submission_from_deep_link() has been ported to app/handlers/emergency.py
# (rescue_start now accepts `command: CommandObject` and calls them) since
# that is the handler that actually owns /start in production -- this copy
# was silently swallowing every task/activity submission deep link before
# that fix. Kept registered here only as a defense-in-depth fallback, per
# the same "legacy handler kept as emergency backup, not deleted" decision
# already applied elsewhere to app/handlers/emergency.py's own reply-keyboard
# rescue handlers.
@router.message(CommandStart(), F.chat.type == "private")
@router.message(Command("menu"), F.chat.type == "private")
async def start(
    message: Message,
    bot: Bot,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
    command: CommandObject | None = None,
) -> None:
    await state.clear()
    subscribed = await _subscription_ok(bot, message.from_user.id, settings)
    if subscribed is None:
        if _approved_existing_user(user):
            await show_home(message, user, settings)
            return
        await message.answer(
            getattr(
                texts,
                "SUBSCRIPTION_CHECK_UNAVAILABLE",
                "Проверка подписки временно недоступна. Попробуйте позже или напишите администратору.",
            ),
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if not subscribed:
        await message.answer(
            texts.SUBSCRIPTION_REQUIRED,
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if user is None:
        await message.answer(ux_texts.WELCOME_START, reply_markup=registration_keyboard())
        return
    await show_home(message, user, settings)


@router.callback_query(F.data == "subscription:check")
async def check_subscription(
    call: CallbackQuery,
    bot: Bot,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    await call.answer()
    await state.clear()
    subscribed = await _subscription_ok(bot, call.from_user.id, settings)
    if subscribed is None:
        if _approved_existing_user(user):
            await show_home(call.message, user, settings)
            return
        await call.message.answer(
            getattr(
                texts,
                "SUBSCRIPTION_CHECK_UNAVAILABLE",
                "Проверка подписки временно недоступна. Попробуйте позже или напишите администратору.",
            ),
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if not subscribed:
        await call.message.answer(
            texts.SUBSCRIPTION_CHECK_FAILED,
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if user is None:
        await call.message.answer(
            texts.SUBSCRIPTION_CONFIRMED, reply_markup=registration_keyboard()
        )
    else:
        await show_home(call.message, user, settings)


@router.callback_query(F.data == "menu:main")
async def main_menu_callback(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    await call.answer()
    await state.clear()
    if user is None:
        await call.message.answer(ux_texts.WELCOME_START, reply_markup=registration_keyboard())
        return
    await show_home(call.message, user, settings)


@router.message(Command("rules"), F.chat.type == "private")
async def private_rules(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CHAT_RULES)
