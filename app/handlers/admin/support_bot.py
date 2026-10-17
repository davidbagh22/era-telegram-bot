"""Private native inbox; existing UserQuestion records and delivery ledger."""
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.models import User, UserQuestion
from app.services.admin_dashboard_service import has_dashboard_access
from app.services.audit_service import audit
from app.services.notification_service import safe_answer_media
from app.services.scheduler_service import deliver_support_answers
from app.utils import texts

router = Router(name='native_support_inbox')
PAGE_SIZE = 8
STATUS_LABELS = {'new': 'Ожидает ответа', 'open': 'В работе', 'answer_pending': 'Ответ в очереди',
                 'answered': 'Ответ доставлен', 'answer_failed': 'Ответ не доставлен',
                 'answer_review': 'Доставка требует проверки'}


class SupportAnswer(StatesGroup):
    text = State()


async def _guard(event, user, settings):
    if has_dashboard_access(user, settings, event.from_user.id):
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
        UserQuestion.status.in_(('new', 'open')).desc(), UserQuestion.created_at, UserQuestion.id)
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
    rows.append([InlineKeyboardButton(text='← Админ-панель', callback_data='admin:panel')])
    await message.answer(f'💬 Обращения · {total}\n\nСначала показаны обращения, которые ожидают ответа.',
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(Command('support_admin'))
async def support_command(message: Message, user: User | None, settings: Settings, session: AsyncSession):
    if await _guard(message, user, settings):
        await show_inbox(message, session)


@router.callback_query(F.data == 'admin:questions')
@router.callback_query(F.data.regexp(r'^admin:support:page:\d+$'))
async def support_list(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession):
    if not await _guard(call, user, settings):
        return
    await call.answer()
    await show_inbox(call.message, session, page=int(call.data.rsplit(':', 1)[-1]) if ':page:' in call.data else 0)


@router.callback_query(F.data.regexp(r'^admin:support:(item|reply|file):\d+$'))
async def support_item(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    if not await _guard(call, user, settings):
        return
    item = await session.get(UserQuestion, int(call.data.rsplit(':', 1)[-1]))
    if item is None:
        await call.answer('Обращение не найдено.', show_alert=True)
        return
    await call.answer()
    if ':file:' in call.data:
        if item.file_id and not await safe_answer_media(call.message, item.file_id, caption=f'Вложение к обращению #{item.id}'):
            await call.message.answer('Telegram не передал вложение. Текст обращения сохранён.')
        return
    if ':reply:' in call.data:
        if item.status not in {'new', 'open'} or item.admin_answer:
            await call.message.answer('Ответ уже сохранён. Откройте актуальную карточку.')
            return
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
    if not await _guard(message, user, settings):
        return
    answer = (message.text or '').strip()
    if not answer or len(answer) > 1500 or answer.startswith('/'):
        await message.answer('Напишите ответ от 1 до 1500 символов или /cancel.')
        return
    item_id = (await state.get_data()).get('support_question_id')
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
