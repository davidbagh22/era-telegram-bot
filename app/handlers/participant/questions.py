import logging

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.models import User
from app.keyboards.common import yes_no_keyboard
from app.keyboards.faq import get_faq_answer_keyboard
from app.services.support_service import create_support_question, deliver_support_intake_notices
from app.services.support_service import (CATEGORIES, append_support_message, support_actor,
    support_thread, deliver_support_thread_messages, support_attachment, support_message_input)
from app.services.feature_flags import Feature, feature_enabled
from app.handlers.support_thread_views import show_my_support, show_support_thread
from app.states.question import QuestionStates
from app.utils import texts
from app.utils.constants import ApplicationStatus
from app.utils.validators import clean_text

router = Router(name="questions")
logger = logging.getLogger(__name__)


async def _begin_question(
    message: Message, state: FSMContext, user: User | None, faq_context: dict | None = None,
    settings: Settings | None = None,
) -> None:
    if not user or user.application_status != ApplicationStatus.APPROVED or user.is_blocked or user.is_archived:
        await message.answer(texts.APPLICATION_PENDING)
        return
    await state.clear()
    if settings and feature_enabled(settings, Feature.SUPPORT_THREADS, user.telegram_id) and not faq_context:
        await state.set_state(QuestionStates.category)
        await message.answer('💬 Обращение в ЭРА\n\nВыберите тему. Переписку видите вы и уполномоченные администраторы. '
            'Обращение не анонимное. Ориентир первого ответа — 24 часа.',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=label, callback_data=f'support:category:{key}')] for key, label in CATEGORIES.items()
            ] + [[InlineKeyboardButton(text='💬 Мои обращения', callback_data='support:mine:page:0')]]))
        return
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
    message: Message, state: FSMContext, user: User | None, settings: Settings
) -> None:
    await _begin_question(message, state, user, settings=settings)


@router.callback_query(F.data == "question:start")
async def question_start(
    call: CallbackQuery, state: FSMContext, user: User | None, faq_context: dict | None = None,
    settings: Settings | None = None,
) -> None:
    await call.answer()
    context = faq_context or (await state.get_data()).get("faq_context")
    await _begin_question(call.message, state, user, context, settings)


@router.callback_query(QuestionStates.category, F.data.regexp(r'^support:category:(general|events|projects|points|access)$'))
async def question_category(call: CallbackQuery, state: FSMContext, user: User | None, settings: Settings, session: AsyncSession):
    try:
        await support_actor(session, user.id if user else None, settings)
    except PermissionError:
        await call.answer(texts.NO_ACCESS, show_alert=True)
        return
    await call.answer()
    await state.update_data(support_category=call.data.rsplit(':', 1)[-1])
    await state.set_state(QuestionStates.text)
    await call.message.answer(texts.QUESTION_START)


@router.message(Command('my_questions'))
@router.message(F.text == '💬 Мои обращения')
async def my_questions(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    try:
        actor = await support_actor(session, user.id if user else None, settings)
    except PermissionError:
        await message.answer('История обращений пока недоступна для вашего профиля.')
        return
    await state.clear()
    await show_my_support(message, session, actor)



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
        question, created = await create_support_question(
            session, user_id=user.id, source_key=source_key,
            text=(f"Тема: {topic}\n\n" if topic else "") + value, file_id=file_id,
            context={"category": context.get("category"), "question": context.get("question")} if context else None,
        )
    except PermissionError:
        await state.clear()
        await message.answer(texts.APPLICATION_PENDING)
        return
    if created and settings and feature_enabled(settings, Feature.SUPPORT_THREADS, user.telegram_id):
        question.category = data.get('support_category', 'general')
    await session.commit()
    await state.clear()
    await message.answer(
        texts.QUESTION_DONE + f"\n\nНомер обращения: #{question.id}",
        reply_markup=(get_faq_answer_keyboard(context["back"]) if context else
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='💬 Мои обращения', callback_data='support:mine:page:0')]])
            if feature_enabled(settings, Feature.SUPPORT_THREADS, user.telegram_id) else None),
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




@router.callback_query(F.data.regexp(r'^support:mine:(page:\d+|item:\d+|history:\d+:\d+|reply:\d+:\d+|file:\d+:\d+|attachment:\d+:\d+)$'))
async def my_question_action(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    try:
        actor = await support_actor(session, user.id if user else None, settings)
        parts = call.data.split(':')
        action, item_id = parts[2], int(parts[3])
        if action == 'page':
            await state.clear()
            await call.answer()
            await show_my_support(call.message, session, actor, page=item_id)
            return
        item = await support_thread(session, item_id, actor.id, settings)
        if action == 'reply':
            revision = int(parts[4])
            if revision != item.thread_revision or item.status == 'thread_closed':
                await call.answer('Карточка изменилась. Откройте её заново.', show_alert=True)
                return
            await state.set_state(QuestionStates.followup)
            await state.update_data(support_question_id=item.id, support_thread_revision=revision)
            await call.message.answer(f'Дополните обращение #{item.id}: текст до 1500 символов, фото или документ. '
                'К файлу можно добавить подпись.\n/cancel — отменить.')
        elif action in {'file', 'attachment'}:
            from app.services.notification_service import safe_answer_media
            file_id = (await support_attachment(session, settings, question_id=item.id,
                message_id=int(parts[4]), actor_id=actor.id)) if action == 'attachment' else item.file_id
            if file_id and not await safe_answer_media(call.message, file_id, caption=f'Вложение к обращению #{item.id}'):
                await call.message.answer('Файл сохранён, но Telegram сейчас не даёт открыть его. Попробуйте позже.')
        else:
            await state.clear()
            await show_support_thread(call.message, session, settings, question_id=item.id, actor_id=actor.id,
                page=int(parts[4]) if action == 'history' else None)
        await call.answer()
    except PermissionError:
        await call.answer('Обращение недоступно.', show_alert=True)


@router.message(QuestionStates.followup)
async def question_followup(message: Message, state: FSMContext, user: User | None, settings: Settings, session: AsyncSession, bot: Bot):
    try:
        value, file_id = support_message_input(message)
    except ValueError:
        await message.answer('Отправьте текст до 1500 символов, фото или документ с подписью. /cancel — отменить.')
        return
    data = await state.get_data()
    try:
        await append_support_message(session, settings, question_id=data.get('support_question_id'),
            actor_id=user.id if user else None, staff=False, text=value,
            source_key=f'{message.chat.id}:{message.message_id}', expected_revision=data.get('support_thread_revision'), file_id=file_id)
        await session.commit()
    except (PermissionError, ValueError):
        await session.rollback()
        await state.clear()
        await message.answer('Карточка изменилась или обращение недоступно. Откройте /my_questions и проверьте историю.')
        return
    await state.clear()
    await message.answer('✅ Дополнение сохранено. Ответ появится здесь и в истории /my_questions.')
    try:
        await deliver_support_thread_messages(bot, settings, async_sessionmaker(session.bind, expire_on_commit=False))
    except Exception as exc:
        logger.warning('Support thread delivery deferred code=%s', type(exc).__name__)
