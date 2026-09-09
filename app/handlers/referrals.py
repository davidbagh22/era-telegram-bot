from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.handlers.registration import registration_start
from app.keyboards.registration import consent_keyboard, referral_code_keyboard
from app.services.consent_policy import CONSENT_SUMMARY
from app.services.referral_service import validate_referral_code
from app.services.subscription_service import SubscriptionCheckError, is_channel_member
from app.states.registration import RegistrationStates
from app.utils import texts

router = Router(name="referrals")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


def _referral_registration_keyboard(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Начать регистрацию",
                    callback_data=f"registration:ref:start:{code}",
                )
            ]
        ]
    )


def _referral_subscription_keyboard(channel_url: str, code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на канал ЭРА", url=channel_url)],
            [
                InlineKeyboardButton(
                    text="Проверить подписку",
                    callback_data=f"registration:ref:start:{code}",
                )
            ],
        ]
    )


async def _return_to_consent(message: Message, state: FSMContext, *, code: str | None) -> None:
    await state.set_state(RegistrationStates.consent)
    prefix = (
        f"🎁 Код друга {code} сохранён.\n\n"
        "После одобрения вашей регистрации пригласивший получит +30 баллов, "
        "а после вашего первого подтверждённого участия в ЭРА — ещё +70.\n\n"
        if code
        else ""
    )
    await message.answer(f"{prefix}{CONSENT_SUMMARY}", reply_markup=consent_keyboard())


@router.message(
    CommandStart(),
    F.text.regexp(r"^/start(?:@\w+)?\s+ref_\d{6}\s*$"),
)
async def referral_deep_link(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    user,
) -> None:
    raw = (command.args or "").strip()
    code = raw.removeprefix("ref_")
    try:
        code_row, _ = await validate_referral_code(
            session,
            code,
            telegram_id=message.from_user.id,
        )
    except ValueError:
        await message.answer(
            "Код приглашения не найден или больше не доступен. "
            "Можно продолжить обычную регистрацию через /start."
        )
        return

    if user is not None:
        await message.answer(
            "Вы уже зарегистрированы в ЭРА. Код приглашения применяется только при первой регистрации."
        )
        return

    await state.clear()
    await message.answer(
        "🔥 Вас пригласили в ЭРА.\n\n"
        f"Код приглашения {code_row.code} уже привязан к этой регистрации — "
        "вручную вводить его не нужно. При желании позже его можно изменить на шаге согласия.\n\n"
        "Нажмите кнопку ниже, чтобы начать.",
        reply_markup=_referral_registration_keyboard(code_row.code),
    )


@router.callback_query(F.data.regexp(r"^registration:ref:start:\d{6}$"))
async def registration_start_with_referral(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    user,
) -> None:
    code = (call.data or "").rsplit(":", 1)[-1]
    try:
        code_row, _ = await validate_referral_code(
            session,
            code,
            telegram_id=call.from_user.id,
        )
    except ValueError:
        await call.answer()
        await call.message.answer(
            "Код приглашения больше не доступен. Начните обычную регистрацию через /start."
        )
        return

    if user is not None:
        await registration_start(call, state, bot, settings, user)
        return

    await call.answer()
    try:
        subscribed = await is_channel_member(bot, call.from_user.id, settings)
    except SubscriptionCheckError:
        await call.message.answer(
            getattr(
                texts,
                "SUBSCRIPTION_CHECK_UNAVAILABLE",
                "Проверка подписки временно недоступна. Попробуйте позже или напишите администратору.",
            ),
            reply_markup=_referral_subscription_keyboard(
                settings.era_channel_url,
                code_row.code,
            ),
        )
        return

    if not subscribed:
        await call.message.answer(
            texts.SUBSCRIPTION_REQUIRED,
            reply_markup=_referral_subscription_keyboard(
                settings.era_channel_url,
                code_row.code,
            ),
        )
        return

    # registration_start() normally clears FSM data. For a referral deep link,
    # start the same first registration step ourselves so the validated code
    # survives all the way to user creation.
    await state.clear()
    await state.update_data(referral_code=code_row.code)
    await state.set_state(RegistrationStates.first_name)
    await call.message.answer(texts.REGISTRATION_INTRO)


@router.callback_query(RegistrationStates.consent, F.data == "reg:ref:start")
async def start_referral_code(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(RegistrationStates.referral_code)
    await call.message.answer(
        "🎁 Код друга\n\n"
        "Если вас пригласил участник ЭРА, отправьте его 6-значный код одним сообщением.\n\n"
        "После одобрения вашей регистрации пригласивший получит +30 баллов. "
        "После вашего первого подтверждённого участия в ЭРА — ещё +70.",
        reply_markup=referral_code_keyboard(),
    )


@router.callback_query(RegistrationStates.referral_code, F.data == "reg:ref:use")
async def use_prefilled_referral_code(call: CallbackQuery, state: FSMContext) -> None:
    """Keep an already validated referral code and return to consent."""
    await call.answer()
    data = await state.get_data()
    code = data.get("referral_code")
    if not code:
        await call.message.answer(
            "Сохранённого кода нет. Отправьте 6-значный код друга сообщением.",
            reply_markup=referral_code_keyboard(),
        )
        return
    await _return_to_consent(call.message, state, code=str(code))


@router.callback_query(RegistrationStates.referral_code, F.data == "reg:ref:change")
async def change_prefilled_referral_code(call: CallbackQuery, state: FSMContext) -> None:
    """Discard the current prefill and wait for a new validated code."""
    await call.answer()
    await state.update_data(referral_code=None)
    await call.message.answer(
        "Отправьте новый 6-значный код друга одним сообщением.",
        reply_markup=referral_code_keyboard(),
    )


@router.callback_query(RegistrationStates.referral_code, F.data == "reg:ref:skip")
async def skip_referral_code(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.update_data(referral_code=None)
    await _return_to_consent(call.message, state, code=None)


@router.callback_query(RegistrationStates.referral_code, F.data == "reg:ref:back")
async def back_from_referral_code(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    data = await state.get_data()
    await _return_to_consent(call.message, state, code=data.get("referral_code"))


@router.message(RegistrationStates.referral_code)
async def save_referral_code(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    raw = message.text or ""
    try:
        code_row, _ = await validate_referral_code(
            session,
            raw,
            telegram_id=message.from_user.id,
        )
    except ValueError as exc:
        reason = str(exc)
        text = {
            "invalid_referral_code": "Код состоит ровно из 6 цифр. Проверьте и отправьте ещё раз.",
            "referral_code_not_found": "Такого кода нет. Проверьте цифры у друга и попробуйте ещё раз.",
            "self_referral_not_allowed": "Свой код использовать нельзя.",
        }.get(reason, "Не удалось проверить код. Попробуйте ещё раз.")
        await message.answer(text, reply_markup=referral_code_keyboard())
        return

    await state.update_data(referral_code=code_row.code)
    await _return_to_consent(message, state, code=code_row.code)
