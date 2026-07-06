from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PointTransaction, User
from app.services.points_service import total_points
from app.states.point_transfer import PointTransferStates
from app.utils.constants import ApplicationStatus

router = Router(name="point_transfer")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data="points:transfer:confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="points:transfer:cancel")],
        ]
    )


async def _recipient(session: AsyncSession, value: str) -> User | None:
    clean = value.strip().removeprefix("@")
    if clean.isdigit():
        target = await session.scalar(select(User).where(User.telegram_id == int(clean)))
        if target:
            return target
    return await session.scalar(select(User).where(or_(User.username == clean, User.username == value.strip())))


@router.callback_query(F.data == "points:transfer:start")
async def transfer_start_callback(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    await call.answer()
    if not _approved(user):
        return
    await state.set_state(PointTransferStates.recipient)
    await call.message.answer("Кому передать баллы? Отправьте username участника: @username")


@router.message(F.text == "/give_points")
async def transfer_start_command(message: Message, user: User | None, state: FSMContext) -> None:
    if not _approved(user):
        return
    await state.set_state(PointTransferStates.recipient)
    await message.answer("Кому передать баллы? Отправьте username участника: @username")


@router.message(PointTransferStates.recipient)
async def transfer_recipient(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    if not _approved(user):
        return
    recipient = await _recipient(session, message.text or "")
    if recipient is None or not _approved(recipient):
        await message.answer("Не нашёл активного участника. Проверьте username и попробуйте ещё раз.")
        return
    if recipient.id == user.id:
        await message.answer("Себе баллы передавать нельзя.")
        return
    await state.update_data(
        recipient_id=recipient.id,
        recipient_name=f"{recipient.first_name} {recipient.last_name or ''}".strip(),
    )
    await state.set_state(PointTransferStates.amount)
    await message.answer("Сколько баллов передать? Укажите целое число.")


@router.message(PointTransferStates.amount)
async def transfer_amount(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    if not _approved(user):
        return
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите целое число.")
        return
    if amount <= 0:
        await message.answer("Количество должно быть больше нуля.")
        return
    balance = await total_points(session, user.id)
    if amount > balance:
        await message.answer(f"Недостаточно баллов. Ваш баланс: {balance}.")
        return
    data = await state.get_data()
    await state.update_data(amount=amount)
    await state.set_state(PointTransferStates.confirm)
    await message.answer(
        f"Подтвердите передачу: {amount} баллов участнику {data['recipient_name']}.",
        reply_markup=_confirm_keyboard(),
    )


@router.callback_query(PointTransferStates.confirm, F.data == "points:transfer:confirm")
async def transfer_confirm(call: CallbackQuery, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    await call.answer()
    if not _approved(user):
        return
    data = await state.get_data()
    amount = int(data.get("amount", 0))
    recipient_id = int(data.get("recipient_id", 0))
    balance = await total_points(session, user.id)
    if amount <= 0 or amount > balance or recipient_id == user.id:
        await state.clear()
        await call.message.answer("Передача отменена: данные устарели или баланса уже недостаточно.")
        return
    recipient = await session.get(User, recipient_id)
    if recipient is None or not _approved(recipient):
        await state.clear()
        await call.message.answer("Передача отменена: участник больше недоступен.")
        return
    session.add(
        PointTransaction(
            user_id=user.id,
            points=-amount,
            reason=f"Передача баллов участнику {recipient.first_name} {recipient.last_name or ''}".strip(),
            approved_by=user.id,
        )
    )
    session.add(
        PointTransaction(
            user_id=recipient.id,
            points=amount,
            reason=f"Получено от {user.first_name} {user.last_name or ''}".strip(),
            approved_by=user.id,
        )
    )
    await session.flush()
    await state.clear()
    await call.message.answer("Баллы переданы ✅")


@router.callback_query(F.data == "points:transfer:cancel")
async def transfer_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await call.message.answer("Передача отменена.")
