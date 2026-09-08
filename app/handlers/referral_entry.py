from aiogram import F, Bot, Router
from aiogram.filters import CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.handlers import emergency, registration, start
from app.services.referral_service import validate_referral_code

router = Router(name="referral_entry")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

REFERRAL_PREFIX = "ref_"


async def _referral_from_start(
    message: Message,
    session: AsyncSession,
    command: CommandObject | None,
) -> str | None:
    if command is None or not command.args or not command.args.startswith(REFERRAL_PREFIX):
        return None
    raw_code = command.args[len(REFERRAL_PREFIX):]
    try:
        code_row, _ = await validate_referral_code(
            session,
            raw_code,
            telegram_id=message.from_user.id,
        )
    except ValueError:
        return None
    return code_row.code


async def _restore_referral_code(
    state: FSMContext,
    code: str | None,
    *,
    user: User | None,
) -> None:
    if code and user is None:
        await state.update_data(referral_code=code)


@router.message(StateFilter("*"), CommandStart())
async def referral_aware_start(
    message: Message,
    bot: Bot,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
    command: CommandObject | None = None,
) -> None:
    """Keep a valid referral payload while delegating /start to the production owner."""
    code = (
        await _referral_from_start(message, session, command)
        if user is None
        else None
    )
    await emergency.rescue_start(
        message,
        bot,
        user,
        settings,
        state,
        session,
        command,
    )
    await _restore_referral_code(state, code, user=user)


@router.callback_query(F.data == "subscription:check")
async def referral_aware_subscription_check(
    call: CallbackQuery,
    bot: Bot,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    code = data.get("referral_code")
    await start.check_subscription(call, bot, user, settings, state)
    await _restore_referral_code(state, str(code) if code else None, user=user)


@router.callback_query(F.data == "registration:start")
async def referral_aware_registration_start(
    call: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    user: User | None,
) -> None:
    data = await state.get_data()
    code = data.get("referral_code")
    await registration.registration_start(call, state, bot, settings, user)
    await _restore_referral_code(state, str(code) if code else None, user=user)
