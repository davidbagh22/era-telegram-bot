from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User, UserQuestion
from app.services.notification_service import safe_send
from app.states.question import AdminQuestionStates
from app.utils import texts
from app.utils.constants import Role
from app.utils.validators import clean_text

router = Router(name="admin_questions_flow")


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (
            user
            and not user.is_blocked
            and not user.is_archived
            and any(g.is_active and g.permission == "broadcasts.create" for g in (user.permission_grants or []))
        )
    )


async def _guard(event: CallbackQuery | Message, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    if not _is_admin(user, settings, telegram_id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def _append_history(current: str | None, author: str, text: str) -> str:
    prefix = (current or "").strip()
    line = f"{author}: {text.strip()}"
    return (prefix + "\n\n" + line).strip() if prefix else line


def _admin_question_keyboard(question_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ответить", callback_data=f"admin:question:answer:{question_id}")],
            [InlineKeyboardButton(text="История переписки", callback_data=f"admin:question:history:{question_id}")],
            [InlineKeyboardButton(text="Направить другому", callback_data=f"admin:question:forward:{question_id}")],
            [InlineKeyboardButton(text="Закрыть вопрос", callback_data=f"admin:question:close:{question_id}")],
            [InlineKeyboardButton(text="← Назад", callback_data="admin:questions")],
        ]
    )


def _user_resolved_keyboard(question_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Вопрос решён", callback_data=f"question:resolved:yes:{question_id}")],
            [InlineKeyboardButton(text="💬 Продолжить вопрос", callback_data=f"question:resolved:no:{question_id}")],
        ]
    )


@router.callback_query(F.data == "admin:questions")
async def questions_list(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    items = (
        await session.scalars(
            select(UserQuestion)
            .where(UserQuestion.status.in_(["new", "open", "answered", "forwarded"]))
            .order_by(UserQuestion.created_at.desc())
            .limit(30)
        )
    ).all()
    if not items:
        await call.message.answer(
            "Новых вопросов нет.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="← Админ-панель", callback_data="admin:panel")]]
            ),
        )
        return
    await call.message.answer(f"💬 Вопросы пользователей: {len(items)}")
    for question in items:
        target = await session.get(User, question.user_id)
        name = f"{target.first_name} {target.last_name or ''}".strip() if target else f"ID {question.user_id}"
        await call.message.answer(
            f"Вопрос #{question.id}\n\n"
            f"Участник: {name}\n"
            f"Статус: {question.status}\n\n"
            f"Последнее сообщение:\n{question.text}",
            reply_markup=_admin_question_keyboard(question.id),
        )


@router.callback_query(F.data.startswith("admin:question:history:"))
async def question_history(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not await _guard(call, user, settings):
        return
    question = await session.get(UserQuestion, int(call.data.rsplit(":", 1)[-1]))
    if not question:
        await call.message.answer("Вопрос не найден")
        return
    await call.message.answer(
        f"История вопроса #{question.id}\n\n{question.admin_answer or question.text}",
        reply_markup=_admin_question_keyboard(question.id),
    )


@router.callback_query(F.data.startswith("admin:question:answer:"))
async def answer_start(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminQuestionStates.answer)
    await state.update_data(question_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer(
        "Напишите ответ участнику. После ответа пользователь сможет нажать: вопрос решён или продолжить переписку.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin:questions")]]
        ),
    )


@router.message(AdminQuestionStates.answer)
async def answer_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    answer = clean_text(message.text or "", 3000)
    if not answer:
        await message.answer(texts.INVALID_INPUT)
        return
    data = await state.get_data()
    question = await session.get(UserQuestion, int(data["question_id"]))
    if not question:
        await state.clear()
        await message.answer("Вопрос не найден")
        return
    question.status = "answered"
    question.admin_answer = _append_history(question.admin_answer, "Админ", answer)
    question.answered_by = user.id if user else None
    target = await session.get(User, question.user_id)
    if target:
        await safe_send(
            bot,
            target.telegram_id,
            f"Ответ команды ЭРА по Вашему вопросу #{question.id}:\n\n{answer}\n\nВопрос решён?",
            reply_markup=_user_resolved_keyboard(question.id),
        )
    await state.clear()
    await message.answer(
        "Ответ отправлен.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="← К вопросам", callback_data="admin:questions")]]
        ),
    )


@router.callback_query(F.data.startswith("admin:question:forward:"))
async def forward_start(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminQuestionStates.forward)
    await state.update_data(question_id=int(call.data.rsplit(":", 1)[-1]))
    await call.message.answer(
        "Кому направить вопрос? Напишите имя ответственного, направление или короткий комментарий.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin:questions")]]
        ),
    )


@router.message(AdminQuestionStates.forward)
async def forward_finish(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(message, user, settings):
        return
    comment = clean_text(message.text or "", 1000)
    if not comment:
        await message.answer(texts.INVALID_INPUT)
        return
    data = await state.get_data()
    question = await session.get(UserQuestion, int(data["question_id"]))
    if not question:
        await state.clear()
        await message.answer("Вопрос не найден")
        return
    question.status = "forwarded"
    question.admin_answer = _append_history(question.admin_answer, "Админ направил", comment)
    target = await session.get(User, question.user_id)
    if target:
        await safe_send(
            bot,
            target.telegram_id,
            "Ваш вопрос направлен другому ответственному на решение. Команда ЭРА вернётся с ответом здесь же.",
            reply_markup=_user_resolved_keyboard(question.id),
        )
    await state.clear()
    await message.answer("Вопрос направлен. История сохранена.", reply_markup=_admin_question_keyboard(question.id))


@router.callback_query(F.data.startswith("admin:question:close:"))
async def close_question(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot
) -> None:
    if not await _guard(call, user, settings):
        return
    question = await session.get(UserQuestion, int(call.data.rsplit(":", 1)[-1]))
    if not question:
        await call.message.answer("Вопрос не найден")
        return
    question.status = "closed"
    target = await session.get(User, question.user_id)
    if target:
        await safe_send(bot, target.telegram_id, f"Вопрос #{question.id} закрыт командой ЭРА.")
    await call.message.answer("Вопрос закрыт.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← К вопросам", callback_data="admin:questions")]]))
