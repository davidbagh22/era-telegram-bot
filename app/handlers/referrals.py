from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.registration import consent_keyboard, referral_code_keyboard
from app.services.referral_service import validate_referral_code
from app.services.consent_policy import CONSENT_SUMMARY
from app.states.registration import RegistrationStates

router = Router(name="referrals")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


async def _return_to_consent(message: Message, state: FSMContext, *, code: str | None) -> None:
    await state.set_state(RegistrationStates.consent)
    prefix = (
        f"🎁 Код друга {code} сохранён.\n\n"
        "После одобрения регистрации и вступления в общий чат вы оба получите по 200 баллов. "
        "После вашего первого подтверждённого мероприятия — ещё по 500 баллов каждому.\n\n"
        if code
        else ""
    )
    await message.answer(f"{prefix}{CONSENT_SUMMARY}", reply_markup=consent_keyboard())


@router.callback_query(RegistrationStates.consent, F.data == "reg:ref:start")
async def start_referral_code(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(RegistrationStates.referral_code)
    await call.message.answer(
        "🎁 Код друга\n\n"
        "Если вас пригласил участник ЭРА, отправьте его 6-значный код одним сообщением.\n\n"
        "Что это даст: после одобрения вашей регистрации и вступления в общий чат — "
        "+200 баллов вам и другу. После вашего первого подтверждённого мероприятия — "
        "ещё +500 каждому.",
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
