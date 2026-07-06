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


def ok(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


def kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Подтвердить", callback_data="points:transfer:confirm")], [InlineKeyboardButton(text="Отмена", callback_data="points:transfer:cancel")]])


async def find_user(session: AsyncSession, text: str) -> User | None:
    value = (text or "").strip().removeprefix("@")
    if value.isdigit():
        return await session.scalar(select(User).where(or_(User.telegram_id == int(value), User.id == int(value))))
    return await session.scalar(select(User).where(User.username == value))


@router.callback_query(F.data == "points:transfer:start")
async def start(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    await call.answer()
    if not ok(user):
        return
    await state.set_state(PointTransferStates.recipient)
    await call.message.answer("Кому передать баллы? Отправьте username участника: @username")


@router.message(PointTransferStates.recipient)
async def recipient(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    if not ok(user):
        return
    target = await find_user(session, message.text or "")
    if target is None or not ok(target) or target.id == user.id:
        await message.answer("Участник не найден или недоступен для передачи баллов.")
        return
    await state.update_data(recipient_id=target.id, recipient_name=f"{target.first_name} {target.last_name or ''}".strip())
    await state.set_state(PointTransferStates.amount)
    await message.answer("Сколько баллов передать? Укажите целое число.")


@router.message(PointTransferStates.amount)
async def amount(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    if not ok(user):
        return
    try:
        value = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите целое число.")
        return
    if value <= 0 or value > 300:
        await message.answer("Можно передать от 1 до 300 баллов за одну операцию.")
        return
    balance = await total_points(session, user.id)
    if value > balance:
        await message.answer(f"Недостаточно баллов. Ваш баланс: {balance}.")
        return
    data = await state.get_data()
    await state.update_data(amount=value)
    await state.set_state(PointTransferStates.confirm)
    await message.answer(f"Подтвердите передачу: {value} баллов участнику {data['recipient_name']}.", reply_markup=kb())


@router.callback_query(PointTransferStates.confirm, F.data == "points:transfer:confirm")
async def confirm(call: CallbackQuery, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    await call.answer()
    if not ok(user):
        return
    data = await state.get_data()
    value = int(data.get("amount", 0))
    target = await session.get(User, int(data.get("recipient_id", 0)))
    if target is None or not ok(target) or target.id == user.id or value <= 0 or value > await total_points(session, user.id):
        await state.clear()
        await call.message.answer("Передача отменена: данные устарели.")
        return
    session.add(PointTransaction(user_id=user.id, points=-value, reason=f"Передача баллов участнику {target.first_name}", approved_by=user.id))
    session.add(PointTransaction(user_id=target.id, points=value, reason=f"Получено от {user.first_name}", approved_by=user.id))
    await session.flush()
    await state.clear()
    await call.message.answer("Баллы переданы ✅")


@router.callback_query(F.data == "points:transfer:cancel")
async def cancel(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await call.message.answer("Передача отменена.")
