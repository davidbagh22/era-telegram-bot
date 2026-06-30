from aiogram import F, Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from app.config import Settings
from app.database.models import User
from app.keyboards.common import registration_keyboard, subscription_keyboard
from app.keyboards.participant import main_menu
from app.services.subscription_service import is_channel_member
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role

router = Router(name="start")


async def show_home(message: Message, user: User, settings: Settings) -> None:
    if user.is_blocked:
        await message.answer(texts.BLOCKED)
        return
    if user.application_status == ApplicationStatus.PENDING:
        await message.answer(texts.APPLICATION_PENDING)
        return
    if user.application_status == ApplicationStatus.REJECTED:
        await message.answer(texts.APPLICATION_REJECTED)
        return
    if user.application_status == ApplicationStatus.NEEDS_INFO:
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(
        texts.MAIN_MENU,
        reply_markup=main_menu(
            settings.era_channel_url,
            privileged=user.role in PRIVILEGED_ROLES,
            admin=user.role == Role.ADMIN,
            mini_app_url=settings.effective_base_url or None,
        ),
    )


@router.message(CommandStart())
@router.message(Command("menu"))
async def start(
    message: Message,
    bot: Bot,
    user: User | None,
    settings: Settings,
) -> None:
    subscribed = await is_channel_member(bot, message.from_user.id, settings)
    if not subscribed:
        await message.answer(
            texts.SUBSCRIPTION_REQUIRED,
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if user is None:
        await message.answer(texts.WELCOME, reply_markup=registration_keyboard())
        return
    await show_home(message, user, settings)


@router.callback_query(F.data == "subscription:check")
async def check_subscription(
    call: CallbackQuery,
    bot: Bot,
    user: User | None,
    settings: Settings,
) -> None:
    await call.answer()
    if not await is_channel_member(bot, call.from_user.id, settings):
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
    call: CallbackQuery, user: User | None, settings: Settings
) -> None:
    await call.answer()
    if user is None:
        await call.message.answer(texts.WELCOME, reply_markup=registration_keyboard())
        return
    await show_home(call.message, user, settings)
