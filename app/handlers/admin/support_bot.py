"""Private native inbox; existing UserQuestion records and delivery ledger."""
import logging
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.models import User, UserQuestion
from app.services.staff_access_service import can_operate_queue
from app.services.audit_service import audit
from app.services.notification_service import safe_answer_media
from app.services.scheduler_service import deliver_support_answers
from app.services.support_service import (CATEGORIES, append_support_message, support_thread,
    update_support_thread, deliver_support_thread_messages, support_assignees,
    support_attachment, support_message_input)
from app.services.feature_flags import Feature, feature_enabled
from app.handlers.support_thread_views import show_support_thread, STATUS_LABELS as THREAD_LABELS
from app.utils import texts

router = Router(name='native_support_inbox')
PAGE_SIZE = 8
STATUS_LABELS = {'new': 'Ожидает ответа', 'open': 'В работе', 'answer_pending': 'Ответ в очереди',
                 'answered': 'Ответ доставлен', 'answer_failed': 'Ответ не доставлен',
                 'answer_review': 'Доставка требует проверки'}
STATUS_LABELS.update(THREAD_LABELS)
logger = logging.getLogger(__name__)


class SupportAnswer(StatesGroup):
    text = State()


async def _guard(event, user, settings, session):
    if await can_operate_queue(session, user, settings, "support.manage"):
        return True
    if isinstance(event, CallbackQuery):
        await event.answer(texts.NO_ACCESS, show_alert=True)
    else:
        await event.answer(texts.NO_ACCESS)
    return False


async def show_inbox(message, session, *, page=0):
    total = int(await session.scalar(select(func.count()).select_from(UserQuestion)) or 0)
    page = min(max(0, page), max(0, (total-1)//PAGE_SIZE))
    items = list((await session.scalars(select(UserQuestion).order_by(
        UserQuestion.status.in_(('new', 'open', 'thread_waiting')).desc(), UserQuestion.created_at, UserQuestion.id)
        .offset(page*PAGE_SIZE).limit(PAGE_SIZE))).all())
    rows = [[InlineKeyboardButton(text=f'#{item.id} · {STATUS_LABELS.get(item.status, item.status)}',
                                  callback_data=f'admin:support:item:{item.id}')] for item in items]
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(text='←', callback_data=f'admin:support:page:{page-1}'))
    if (page+1)*PAGE_SIZE < total:
        navigation.append(InlineKeyboardButton(text='→', callback_data=f'admin:support:page:{page+1}'))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text='← Рабочие разделы', callback_data='staff:home')])
    await message.answer(f'💬 Обращения · {total}\n\nСначала показаны обращения, которые ожидают ответа.',
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(Command('support_admin'))
async def support_command(message: Message, user: User | None, settings: Settings, session: AsyncSession):
    if await _guard(message, user, settings, session):
        await show_inbox(message, session)


@router.callback_query(F.data == 'admin:questions')
@router.callback_query(F.data.regexp(r'^admin:support:page:\d+$'))
async def support_list(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession):
    if not await _guard(call, user, settings, session):
        return
    await call.answer()
    await show_inbox(call.message, session, page=int(call.data.rsplit(':', 1)[-1]) if ':page:' in call.data else 0)


@router.callback_query(F.data.regexp(r'^admin:support:(item|reply|file):\d+$'))
async def support_item(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    if not await _guard(call, user, settings, session):
        return
    item = await session.get(UserQuestion, int(call.data.rsplit(':', 1)[-1]))
    if item is None:
        await call.answer('Обращение не найдено.', show_alert=True)
        return
    await call.answer()
    owner = await session.get(User, item.user_id)
    owner_enabled = owner and feature_enabled(settings, Feature.SUPPORT_THREADS, owner.telegram_id)
    if (user and feature_enabled(settings, Feature.SUPPORT_THREADS, call.from_user.id)
            and (owner_enabled or item.status.startswith('thread_')) and ':file:' not in call.data):
        if ':reply:' in call.data:
            await state.clear()
            await state.set_state(SupportAnswer.text)
            await state.update_data(support_question_id=item.id, support_thread_revision=item.thread_revision)
            await call.message.answer(f'Ответ на обращение #{item.id}: текст до 1500 символов, фото или документ с подписью.\n/cancel — отменить.')
        else:
            await state.clear()
            try:
                await show_support_thread(call.message, session, settings, question_id=item.id, actor_id=user.id, staff=True)
            except PermissionError:
                await call.message.answer(texts.NO_ACCESS)
        return
    if ':file:' in call.data:
        if item.file_id and not await safe_answer_media(call.message, item.file_id, caption=f'Вложение к обращению #{item.id}'):
            await call.message.answer('Telegram не передал вложение. Текст обращения сохранён.')
        return
    if ':reply:' in call.data:
        if item.status not in {'new', 'open'} or item.admin_answer:
            await call.message.answer('Ответ уже сохранён. Откройте актуальную карточку.')
            return
        await state.clear()
        await state.set_state(SupportAnswer.text)
        await state.update_data(support_question_id=item.id)
        await call.message.answer(f'Напишите ответ на обращение #{item.id}. Этот текст получит участник.\n\n/cancel — отменить.')
        return
    author = await session.get(User, item.user_id)
    name = f'{author.first_name} {author.last_name or ""}'.strip() if author else 'Профиль недоступен'
    body = (f'💬 Обращение #{item.id}\n{STATUS_LABELS.get(item.status, item.status)}\n'
            f'От: {name}\n\n{item.text}')
    if item.admin_answer:
        body += f'\n\nОтвет:\n{item.admin_answer}'
    if item.status.startswith('thread_'):
        body += '\n\nПереписка сохранена. Для работы с историей требуется включённый доступ к модулю обращений.'
    rows = []
    if item.status in {'new', 'open'} and not item.admin_answer:
        rows.append([InlineKeyboardButton(text='✍️ Ответить', callback_data=f'admin:support:reply:{item.id}')])
    if item.file_id:
        rows.append([InlineKeyboardButton(text='📎 Вложение', callback_data=f'admin:support:file:{item.id}')])
    rows.append([InlineKeyboardButton(text='← Обращения', callback_data='admin:questions')])
    chunks = [body[i:i+2000] for i in range(0, len(body), 2000)]
    for index, chunk in enumerate(chunks):
        await call.message.answer(chunk, parse_mode=None,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if index == len(chunks)-1 else None)


@router.message(SupportAnswer.text)
async def support_answer(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext, bot: Bot):
    if not await _guard(message, user, settings, session):
        return
    try:
        answer, file_id = support_message_input(message)
    except ValueError:
        await message.answer('Отправьте ответ до 1500 символов, фото или документ с подписью. /cancel — отменить.')
        return
    item_id = (await state.get_data()).get('support_question_id')
    data = await state.get_data()
    if 'support_thread_revision' in data:
        try:
            await append_support_message(session, settings, question_id=item_id, actor_id=user.id if user else None,
                staff=True, text=answer, source_key=f'{message.chat.id}:{message.message_id}',
                expected_revision=data['support_thread_revision'], file_id=file_id)
            await session.commit()
        except (PermissionError, ValueError):
            await session.rollback()
            await state.clear()
            await message.answer('Карточка изменилась или доступ ограничен. Откройте обращение и проверьте историю перед ответом.')
            return
        await state.clear()
        await message.answer('✅ Ответ сохранён. Его доставка и история доступны в карточке обращения.')
        try:
            await deliver_support_thread_messages(bot, settings, async_sessionmaker(session.bind, expire_on_commit=False))
        except Exception as exc:
            logger.warning('Support thread delivery deferred code=%s', type(exc).__name__)
        return
    if file_id:
        await message.answer('Для этого обращения пока доступен текстовый ответ. Напишите текст или /cancel.')
        return
    item = await session.scalar(select(UserQuestion).where(UserQuestion.id == item_id).with_for_update()
                                .execution_options(populate_existing=True))
    if not item or item.status not in {'new', 'open'} or item.admin_answer:
        await state.clear()
        await message.answer('Ответ уже сохранён другим администратором. Обновите карточку.')
        return
    item.admin_answer, item.answered_by, item.status = answer, user.id if user else None, 'answer_pending'
    await audit(session, actor_id=user.id if user else None, action='support.answered',
                entity_type='question', entity_id=item.id, new_value={'status': 'answer_pending'})
    await session.commit()
    await state.clear()
    await deliver_support_answers(bot, settings, async_sessionmaker(session.bind, expire_on_commit=False))
    await message.answer('✅ Ответ сохранён в очереди доставки. Статус можно проверить в карточке обращения.')


@router.callback_query(F.data.regexp(r'^admin:support:thread:(history|reply|file|attachment|claim|release|close|reopen|categories):\d+:\d+$'))
@router.callback_query(F.data.regexp(r'^admin:support:thread:category:\d+:\d+:(general|events|projects|points|access)$'))
async def support_thread_action(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    if not await _guard(call, user, settings, session):
        return
    parts = call.data.split(':')
    action, question_id, revision = parts[3], int(parts[4]), int(parts[5])
    try:
        item = await support_thread(session, question_id, user.id if user else None, settings, staff=True)
        if action == 'history':
            await state.clear()
            await show_support_thread(call.message, session, settings, question_id=item.id, actor_id=user.id, staff=True, page=revision)
        elif action in {'file', 'attachment'}:
            file_id = (await support_attachment(session, settings, question_id=item.id,
                message_id=revision, actor_id=user.id, staff=True)) if action == 'attachment' else item.file_id
            if file_id and not await safe_answer_media(call.message, file_id, caption=f'Вложение к обращению #{item.id}'):
                await call.message.answer('Файл сохранён, но Telegram сейчас не даёт открыть его. Попробуйте позже.')
        elif action == 'reply':
            if item.thread_revision != revision or item.status == 'thread_closed':
                raise ValueError('stale_thread')
            await state.clear()
            await state.set_state(SupportAnswer.text)
            await state.update_data(support_question_id=item.id, support_thread_revision=revision)
            await call.message.answer(f'Ответ на обращение #{item.id}: текст до 1500 символов, фото или документ с подписью.\n/cancel — отменить.')
        elif action == 'categories':
            await call.message.answer('Выберите тему обращения:', reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=label, callback_data=f'admin:support:thread:category:{item.id}:{revision}:{key}')]
                for key, label in CATEGORIES.items()]))
        else:
            await update_support_thread(session, settings, question_id=item.id, actor_id=user.id,
                expected_revision=revision, action=action, category=parts[6] if action == 'category' else None)
            await session.commit()
            await state.clear()
            await show_support_thread(call.message, session, settings, question_id=item.id, actor_id=user.id, staff=True)
        await call.answer()
    except (PermissionError, ValueError):
        await session.rollback()
        await call.answer('Карточка изменилась или действие недоступно. Откройте обращение заново.', show_alert=True)


@router.callback_query(F.data.regexp(r'^admin:support:thread:(assignees|assign):\d+:\d+:\d+$'))
async def support_assign(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    if not await _guard(call, user, settings, session):
        return
    parts = call.data.split(':')
    action, question_id, revision, target = parts[3], int(parts[4]), int(parts[5]), int(parts[6])
    try:
        item = await support_thread(session, question_id, user.id, settings, staff=True)
        if item.thread_revision != revision or item.status == 'thread_closed':
            raise ValueError('stale_thread')
        if action == 'assign':
            await update_support_thread(session, settings, question_id=question_id, actor_id=user.id,
                expected_revision=revision, action='assign', assignee_id=target)
            await session.commit()
            await state.clear()
            await show_support_thread(call.message, session, settings, question_id=question_id, actor_id=user.id, staff=True)
        else:
            assignees = await support_assignees(session, settings)
            page = min(target, max(0, (len(assignees)-1)//8))
            rows = [[InlineKeyboardButton(text=(f'{actor.first_name} {actor.last_name or ""}'.strip())[:45],
                callback_data=f'admin:support:thread:assign:{item.id}:{revision}:{actor.id}')]
                for actor in assignees[page*8:(page+1)*8]]
            nav = []
            for number, label in ((page-1, '←'), (page+1, '→')):
                if 0 <= number <= (len(assignees)-1)//8:
                    nav.append(InlineKeyboardButton(text=label,
                        callback_data=f'admin:support:thread:assignees:{item.id}:{revision}:{number}'))
            if nav:
                rows.append(nav)
            rows.append([InlineKeyboardButton(text='← Обращение', callback_data=f'admin:support:item:{item.id}')])
            await call.message.answer('👤 Ответственный\n\nВыберите администратора с доступом к обращениям.',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        await call.answer()
    except (PermissionError, ValueError):
        await session.rollback()
        await call.answer('Карточка или права изменились. Откройте обращение заново.', show_alert=True)
