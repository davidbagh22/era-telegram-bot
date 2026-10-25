"""Controls existing campaigns; never creates an alternate delivery pipeline."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Broadcast, User
from app.database.system_models import NotificationDelivery
from app.services.admin_broadcast_service import BroadcastError, control_broadcast
from app.services.admin_dashboard_service import has_dashboard_access
from app.utils import texts

router = Router(name='campaign_control')
LABELS = {'sending': 'Отправляется', 'paused': 'На паузе', 'cancelled': 'Отменена',
          'sent': 'Доставлена', 'partial': 'Часть получателей недоступна', 'review_required': 'Нужна сверка доставки'}


async def show_campaigns(message, session):
    items = list((await session.scalars(select(Broadcast).where(
        Broadcast.audience_filter_json['campaign_key'].as_string().is_not(None))
        .order_by(Broadcast.id.desc()).limit(15))).all())
    rows = [[InlineKeyboardButton(text=f'#{item.id} · {LABELS.get(item.status, item.status)}',
        callback_data=f'admin:campaign:{item.id}:view')] for item in items]
    rows.append([InlineKeyboardButton(text='← Админ-панель', callback_data='admin:panel')])
    await message.answer('📨 Рассылки ЭРА\n\nПоследние 15 кампаний. Пауза и отмена останавливают следующие отправки; '
                         'сообщение, уже переданное Telegram, отозвать нельзя.',
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(Command('campaigns'))
async def campaigns_command(message: Message, user: User | None, settings: Settings, session: AsyncSession):
    if not has_dashboard_access(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return
    await show_campaigns(message, session)


@router.callback_query(F.data == 'admin:campaigns')
async def campaigns_list(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession):
    if not has_dashboard_access(user, settings, call.from_user.id):
        await call.answer(texts.NO_ACCESS, show_alert=True)
        return
    await call.answer()
    await show_campaigns(call.message, session)


@router.callback_query(F.data.regexp(r'^admin:campaign:\d+:(view|pause|resume|cancel)$'))
async def campaign_action(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession):
    if not has_dashboard_access(user, settings, call.from_user.id):
        await call.answer(texts.NO_ACCESS, show_alert=True)
        return
    _, _, raw_id, action = call.data.split(':')
    try:
        if action != 'view':
            await control_broadcast(session, settings, actor=user, campaign_id=int(raw_id), action=action)
            await session.commit()
        item = await session.get(Broadcast, int(raw_id), populate_existing=True)
        if item is None or 'campaign_key' not in (item.audience_filter_json or {}):
            raise BroadcastError('campaign_not_found')
    except BroadcastError:
        await call.answer('Кампания изменилась или недоступна. Обновите список.', show_alert=True)
        return
    await call.answer()
    counts = dict((await session.execute(select(NotificationDelivery.status, func.count()).where(
        NotificationDelivery.delivery_key.like(f'admin-campaign:{item.id}:user:%'))
        .group_by(NotificationDelivery.status))).all())
    rows = []
    if item.status == 'sending':
        rows.append([InlineKeyboardButton(text='⏸ Пауза', callback_data=f'admin:campaign:{item.id}:pause')])
    if item.status == 'paused':
        rows.append([InlineKeyboardButton(text='▶️ Продолжить', callback_data=f'admin:campaign:{item.id}:resume')])
    if item.status in {'sending', 'paused'}:
        rows.append([InlineKeyboardButton(text='⛔ Отменить оставшиеся отправки', callback_data=f'admin:campaign:{item.id}:cancel')])
    rows.append([InlineKeyboardButton(text='🔄 Обновить', callback_data=f'admin:campaign:{item.id}:view'),
                 InlineKeyboardButton(text='← Рассылки', callback_data='admin:campaigns')])
    await call.message.answer(f'📨 Кампания #{item.id}\n{LABELS.get(item.status, item.status)}\n\n'
        f'Аудитория: {len((item.audience_filter_json or {}).get("recipient_ids", []))}\n'
        f'Подтверждено: {counts.get("sent", 0)}\nНеопределённый исход: {counts.get("uncertain", 0)}\n'
        f'Недоступны: {counts.get("blocked", 0)+counts.get("unreachable", 0)}\n\n'
        f'{item.text[:1200]}', parse_mode=None, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
