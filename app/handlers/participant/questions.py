from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
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


@router.callback_query(F.data == "question:start")
async def question_start(
    call: CallbackQuery, state: FSMContext, user: User | None
) -> None:
    await call.answer()
    if not user or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await state.clear()
    await state.set_state(QuestionStates.text)
    await call.message.answer(texts.QUESTION_START)


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
        user_id=user.id, text=data["question_text"], file_id=file_id
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
