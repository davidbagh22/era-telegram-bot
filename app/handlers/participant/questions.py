from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User, UserQuestion
from app.keyboards.common import yes_no_keyboard
from app.services.audit_service import audit
from app.services.notification_service import notify_admins
from app.states.question import QuestionStates
from app.utils import texts
from app.utils.constants import ApplicationStatus
from app.utils.validators import clean_text

router = Router(name="questions")


def _user_question_keyboard(question_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Вопрос решён", callback_data=f"question:resolved:yes:{question_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Продолжить вопрос", callback_data=f"question:resolved:no:{question_id}"
                )
            ],
        ]
    )


def _admin_question_keyboard(question_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ответить", callback_data=f"admin:question:answer:{question_id}")],
            [InlineKeyboardButton(text="История", callback_data=f"admin:question:history:{question_id}")],
            [InlineKeyboardButton(text="Закрыть", callback_data=f"admin:question:close:{question_id}")],
        ]
    )


def _append_history(current: str | None, author: str, text: str) -> str:
    prefix = (current or "").strip()
    line = f"{author}: {text.strip()}"
    return (prefix + "\n\n" + line).strip() if prefix else line


async def _begin_question(
    message: Message, state: FSMContext, user: User | None
) -> None:
    if not user or user.application_status != ApplicationStatus.APPROVED:
        await message.answer(texts.APPLICATION_PENDING)
        return
    await state.clear()
    await state.set_state(QuestionStates.text)
    await message.answer(texts.QUESTION_START)


@router.message(F.text == "💬 Задать вопрос")
async def question_start_button(
    message: Message, state: FSMContext, user: User | None
) -> None:
    await _begin_question(message, state, user)


@router.callback_query(F.data == "question:start")
async def question_start(
    call: CallbackQuery, state: FSMContext, user: User | None
) -> None:
    await call.answer()
    await _begin_question(call.message, state, user)


@router.message(QuestionStates.text)
async def question_text(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 3000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(question_text=value)
    await state.set_state(QuestionStates.attachment_choice)
    await message.answer(
        texts.QUESTION_FILE, reply_markup=yes_no_keyboard("question:file")
    )


async def _save_question(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
    file_id: str | None = None,
) -> None:
    data = await state.get_data()
    question = UserQuestion(
        user_id=user.id,
        text=data["question_text"],
        file_id=file_id,
        status="new",
        admin_answer=_append_history(None, "Пользователь", data["question_text"]),
    )
    session.add(question)
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="question.created",
        entity_type="user_question",
        entity_id=question.id,
    )
    await state.clear()
    await message.answer(texts.QUESTION_DONE)
    await notify_admins(
        bot,
        settings,
        f"Новый вопрос #{question.id} от {user.first_name} {user.last_name or ''}:\n\n{question.text}",
        reply_markup=_admin_question_keyboard(question.id),
    )


@router.callback_query(QuestionStates.attachment_choice, F.data == "question:file:no")
async def question_without_file(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    await call.answer()
    await _save_question(call.message, state, session, user, bot, settings)


@router.callback_query(QuestionStates.attachment_choice, F.data == "question:file:yes")
async def question_with_file(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(QuestionStates.attachment)
    await call.message.answer(texts.QUESTION_SEND_FILE)


@router.message(QuestionStates.attachment, F.photo | F.document)
async def question_attachment(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    settings: Settings,
) -> None:
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    await _save_question(message, state, session, user, bot, settings, file_id)


@router.message(QuestionStates.attachment)
async def question_invalid_attachment(message: Message) -> None:
    await message.answer(texts.QUESTION_SEND_FILE)


@router.callback_query(F.data.regexp(r"^question:resolved:(yes|no):\d+$"))
async def question_resolved(
    call: CallbackQuery, user: User | None, session: AsyncSession, state: FSMContext
) -> None:
    await call.answer()
    if not user or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    _, _, answer, raw_id = call.data.split(":")
    question = await session.get(UserQuestion, int(raw_id))
    if question is None or question.user_id != user.id:
        await call.message.answer(texts.NO_ACCESS)
        return
    if answer == "yes":
        question.status = "closed"
        await state.clear()
        await call.message.answer("Отлично. Вопрос закрыт ✅")
        return
    question.status = "open"
    await state.set_state(QuestionStates.followup)
    await state.update_data(question_id=question.id)
    await call.message.answer("Напишите уточнение. Админ увидит всю историю переписки.")


@router.message(QuestionStates.followup)
async def question_followup(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
) -> None:
    data = await state.get_data()
    question = await session.get(UserQuestion, int(data["question_id"]))
    if question is None or question.user_id != user.id:
        await state.clear()
        await message.answer(texts.NO_ACCESS)
        return
    text = clean_text(message.text or message.caption or "", 3000)
    if not text:
        await message.answer(texts.INVALID_INPUT)
        return
    question.status = "open"
    question.text = text
    question.admin_answer = _append_history(question.admin_answer, "Пользователь", text)
    await state.clear()
    await message.answer("Уточнение отправлено. Команда ЭРА ответит здесь же.")
    await notify_admins(
        bot,
        settings,
        f"Новое уточнение по вопросу #{question.id}\n\n{user.first_name} {user.last_name or ''}:\n{text}",
        reply_markup=_admin_question_keyboard(question.id),
    )
