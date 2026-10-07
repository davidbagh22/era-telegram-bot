from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User, UserQuestion
from app.keyboards.common import yes_no_keyboard
from app.keyboards.faq import get_faq_answer_keyboard
from app.services.audit_service import audit
from app.services.notification_service import notify_admins
from app.states.question import QuestionStates
from app.utils import texts
from app.utils.constants import ApplicationStatus
from app.utils.validators import clean_text

router = Router(name="questions")


async def _begin_question(
    message: Message, state: FSMContext, user: User | None, faq_context: dict | None = None
) -> None:
    if not user or user.application_status != ApplicationStatus.APPROVED or user.is_blocked or user.is_archived:
        await message.answer(texts.APPLICATION_PENDING)
        return
    await state.clear()
    await state.set_state(QuestionStates.text)
    if faq_context:
        await state.update_data(faq_context=faq_context)
    topic = faq_context.get("topic") if faq_context else None
    await message.answer(
        (f"Тема: {topic}\n\n" if topic else "") + texts.QUESTION_START,
        reply_markup=get_faq_answer_keyboard(faq_context["back"]) if faq_context else None,
    )


@router.message(F.text == "💬 Задать вопрос")
async def question_start_button(
    message: Message, state: FSMContext, user: User | None
) -> None:
    await _begin_question(message, state, user)


@router.callback_query(F.data == "question:start")
async def question_start(
    call: CallbackQuery, state: FSMContext, user: User | None, faq_context: dict | None = None
) -> None:
    await call.answer()
    context = faq_context or (await state.get_data()).get("faq_context")
    await _begin_question(call.message, state, user, context)


@router.message(QuestionStates.text)
async def question_text(message: Message, state: FSMContext) -> None:
    value = clean_text(message.text or "", 3000)
    if not value:
        await message.answer(texts.INVALID_INPUT)
        return
    await state.update_data(question_text=value)
    await state.set_state(QuestionStates.attachment_choice)
    markup = yes_no_keyboard("question:file")
    context = (await state.get_data()).get("faq_context")
    if context:
        markup.inline_keyboard.extend(get_faq_answer_keyboard(context["back"]).inline_keyboard)
    await message.answer(texts.QUESTION_FILE, reply_markup=markup)


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
    context = data.get("faq_context")
    topic = context.get("topic") if context else None
    question = UserQuestion(
        user_id=user.id, text=(f"Тема: {topic}\n\n" if topic else "") + data["question_text"], file_id=file_id
    )
    session.add(question)
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="question.created",
        entity_type="user_question",
        entity_id=question.id,
        new_value={"source": "faq", "category": context.get("category"), "question": context.get("question")} if context else None,
    )
    await state.clear()
    await message.answer(
        texts.QUESTION_DONE,
        reply_markup=get_faq_answer_keyboard(context["back"]) if context else None,
    )
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
    context = (await state.get_data()).get("faq_context")
    await call.message.answer(
        texts.QUESTION_SEND_FILE,
        reply_markup=get_faq_answer_keyboard(context["back"]) if context else None,
    )


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
