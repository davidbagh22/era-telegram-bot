import logging

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.models import User
from app.keyboards.common import yes_no_keyboard
from app.keyboards.faq import get_faq_answer_keyboard
from app.services.support_service import create_support_question, deliver_support_intake_notices
from app.states.question import QuestionStates
from app.utils import texts
from app.utils.constants import ApplicationStatus
from app.utils.validators import clean_text

router = Router(name="questions")
logger = logging.getLogger(__name__)


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
    await state.update_data(question_text=value, question_source=f"{message.chat.id}:{message.message_id}")
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
    value = data.get("question_text")
    if not value or user is None:
        await message.answer("Обращение уже принято или ввод отменён. Для нового вопроса откройте форму заново.")
        return
    source_key = data.get("question_source") or f"{message.chat.id}:{message.message_id}"
    try:
        question, _ = await create_support_question(
            session, user_id=user.id, source_key=source_key,
            text=(f"Тема: {topic}\n\n" if topic else "") + value, file_id=file_id,
            context={"category": context.get("category"), "question": context.get("question")} if context else None,
        )
    except PermissionError:
        await state.clear()
        await message.answer(texts.APPLICATION_PENDING)
        return
    await session.commit()
    await state.clear()
    await message.answer(
        texts.QUESTION_DONE + f"\n\nНомер обращения: #{question.id}",
        reply_markup=get_faq_answer_keyboard(context["back"]) if context else None,
    )
    try:
        await deliver_support_intake_notices(bot, settings, async_sessionmaker(session.bind, expire_on_commit=False))
    except Exception as exc:
        logger.warning("Support intake notice deferred code=%s", type(exc).__name__)


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
