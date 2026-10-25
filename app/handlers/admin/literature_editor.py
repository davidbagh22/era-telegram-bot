"""Human-reviewed literary queue; uses the existing book-club publisher."""
import json

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.autocontent_models import GeneralCustomContent
from app.database.models import User
from app.database.system_models import NotificationDelivery
from app.services.staff_access_service import can_manage_literature_settings, can_operate_queue
from app.services.book_club_service import (EDITORIAL_FIELDS, approve_editorial_item, editorial_revision,
    editorial_settings, publish_editorial_item, render_editorial, save_editorial_item, save_editorial_settings)
from app.utils import texts

router = Router(name='literature_editor')


class EditorialInput(StatesGroup):
    text = State()
    time = State()


async def _guard(event, user, settings, session):
    if await can_operate_queue(session, user, settings, "literature.manage"):
        return True
    if isinstance(event, CallbackQuery):
        await event.answer(texts.NO_ACCESS, show_alert=True)
    else:
        await event.answer(texts.NO_ACCESS)
    return False


async def _queue(message, session, page=0, *, manage_settings=True):
    config = await editorial_settings(session)
    total = int(await session.scalar(select(func.count()).select_from(GeneralCustomContent).where(
        GeneralCustomContent.content_type == 'literature')) or 0)
    page = min(max(0, page), max(0, (total-1)//8))
    items = list((await session.scalars(select(GeneralCustomContent).where(
        GeneralCustomContent.content_type == 'literature').order_by(GeneralCustomContent.id.desc()).offset(page*8).limit(8))).all())
    rows = [[InlineKeyboardButton(text=('✅ ' if item.is_skipped else '📗 ' if item.is_enabled else '📝 ')+item.title[:40],
                                   callback_data=f'admin:literature:item:{item.id}')] for item in items]
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(text='←', callback_data=f'admin:literature:page:{page-1}'))
    if (page+1)*8 < total:
        navigation.append(InlineKeyboardButton(text='→', callback_data=f'admin:literature:page:{page+1}'))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text='➕ Новый материал', callback_data='admin:literature:new')])
    if manage_settings:
        rows.extend([
            [InlineKeyboardButton(text='Отключить очередь' if config['enabled'] else 'Включить очередь',
                                  callback_data=f"admin:literature:enabled:{int(not config['enabled'])}"),
             InlineKeyboardButton(text='Продолжить' if config['paused'] else 'Пауза',
                                  callback_data=f"admin:literature:paused:{int(not config['paused'])}")],
            [InlineKeyboardButton(text='⏰ Изменить время', callback_data='admin:literature:time')],
        ])
    rows.append([InlineKeyboardButton(text='← Рабочие разделы', callback_data='staff:home')])
    settings_text = (f"Очередь: {'включена' if config['enabled'] else 'выключена'} · "
        f"{'пауза' if config['paused'] else 'по расписанию'}\n"
        f"Время: {config['hour']:02d}:{config['minute']:02d} МСК\n\n") if manage_settings else ''
    await message.answer(f"📚 Редакция ЭРА · {total} материалов\n\n" + settings_text +
        '📝 Черновик · 📗 Проверено редактором · ✅ Доставлено\n'
        'При включении очередь заменяет автоматический цикл 48 законов. '
        'Без подтверждения редактора материал не публикуется.', reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(Command('literature_admin'))
async def editorial_command(message: Message, user: User | None, settings: Settings, session: AsyncSession):
    if await _guard(message, user, settings, session):
        await _queue(message, session, manage_settings=await can_manage_literature_settings(session, user, settings))


@router.callback_query(F.data.regexp(r'^admin:literature:(?:home|new|time|page:\d{1,5}|enabled:[01]|paused:[01]|item:\d+|edit:\d+|approve:\d+:[0-9a-f]{12}|send:\d+:[0-9a-f]{12})$'))
async def editorial_action(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext, bot: Bot):
    if not await _guard(call, user, settings, session):
        return
    await call.answer()
    parts = call.data.split(':')
    action = parts[2]
    manage_settings = await can_manage_literature_settings(session, user, settings)
    if action in {'enabled', 'paused', 'time'} and not manage_settings:
        await call.message.answer(texts.NO_ACCESS)
        return
    if action in {'home', 'page'}:
        await _queue(call.message, session, int(parts[3]) if action == 'page' else 0,
                     manage_settings=manage_settings)
        return
    if action in {'enabled', 'paused'}:
        await save_editorial_settings(session, actor_id=user.id, **{action: bool(int(parts[3]))})
        await session.commit()
        await _queue(call.message, session)
        return
    if action == 'time':
        await state.set_state(EditorialInput.time)
        await call.message.answer('Отправьте время публикации в МСК: ЧЧ:ММ. /cancel — отменить.')
        return
    if action in {'new', 'edit'}:
        await state.set_state(EditorialInput.text)
        await state.update_data(editorial_item_id=int(parts[3]) if action == 'edit' else None)
        await call.message.answer('Отправьте проверенный текст одним сообщением по шаблону. Избегайте длинных цитат.\n\n'
            'Название: …\nАвтор: …\nВведение: …\nГлавная мысль: …\nВопрос: …\nИсточник: ссылка или издание\n\n'
            'После сохранения будет предпросмотр и отдельное подтверждение редактора. /cancel — отменить.')
        if action == 'new':
            return
    item_id = int(parts[3])
    item = await session.get(GeneralCustomContent, item_id)
    if not item or item.content_type != 'literature':
        await call.message.answer('Материал не найден.')
        return
    if action == 'edit':
        fields = json.loads(item.text)
        await call.message.answer('\n'.join(f'{label}: {fields[key]}' for label, key in EDITORIAL_FIELDS.items() if fields.get(key)))
        return
    try:
        if action == 'approve':
            item = await approve_editorial_item(session, item_id, parts[4], actor_id=user.id)
            await session.commit()
        if action == 'send':
            outcome = await publish_editorial_item(bot, settings, session, item_id, parts[4])
            await session.commit()
            await call.message.answer({'sent': '✅ Выпуск доставлен.', 'already_sent': 'Выпуск уже отправлен, повторной публикации нет.',
                'uncertain': 'Исход отправки неизвестен. Очередь на паузе, нужна сверка с чатом.',
                'topic_missing': 'Тема литературы не настроена. Новая тема не создавалась.'}.get(outcome, 'Отправка не подтверждена. Проверьте историю доставки.'))
    except ValueError:
        await call.message.answer('Материал изменился или ещё не утверждён. Откройте актуальный предпросмотр.')
        return
    revision = editorial_revision(item)
    receipt = await session.scalar(select(NotificationDelivery).where(
        NotificationDelivery.delivery_key == f'general-topic:literature:editorial:{item.content_id}'))
    rows = []
    if not receipt:
        rows.append([InlineKeyboardButton(text='✏️ Редактировать', callback_data=f'admin:literature:edit:{item.id}')])
        rows.append([InlineKeyboardButton(text='✅ Материал проверен', callback_data=f'admin:literature:approve:{item.id}:{revision}')])
    if item.is_enabled and not item.is_skipped and (not receipt or receipt.status not in {'uncertain', 'conflict'}):
        rows.append([InlineKeyboardButton(text='📤 Отправить сейчас', callback_data=f'admin:literature:send:{item.id}:{revision}')])
    rows.append([InlineKeyboardButton(text='← Редакция', callback_data='admin:literature:home')])
    status = f'Доставка: {receipt.status}' if receipt else 'Проверено редактором' if item.is_enabled else 'Черновик · публикация запрещена'
    await call.message.answer(render_editorial(json.loads(item.text))+'\n\n<i>'+status+'</i>', parse_mode='HTML',
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(EditorialInput.text)
@router.message(EditorialInput.time)
async def editorial_input(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    if not await _guard(message, user, settings, session):
        return
    try:
        if await state.get_state() == EditorialInput.time.state:
            if not await can_manage_literature_settings(session, user, settings):
                await state.clear()
                await message.answer(texts.NO_ACCESS)
                return
            import re
            if not re.fullmatch(r'\d{2}:\d{2}', message.text or ''):
                raise ValueError('invalid_time')
            hour, minute = map(int, message.text.split(':'))
            await save_editorial_settings(session, actor_id=user.id, hour=hour, minute=minute)
        else:
            data = await state.get_data()
            item = await save_editorial_item(session, message.text or '', actor_id=user.id,
                                             item_id=data.get('editorial_item_id'))
            await message.answer('📝 Черновик сохранён. Откройте его, проверьте оформление и подтвердите материал.',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                    text='Предпросмотр', callback_data=f'admin:literature:item:{item.id}')]]))
        await session.commit()
        await state.clear()
    except ValueError:
        await message.answer('Не удалось сохранить. Проверьте обязательные поля, длину текста и время. Данные можно исправить и отправить снова.')
