from __future__ import annotations
import json
from datetime import datetime, timezone
from html import escape
from aiogram import F, Router
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select, func
from app.database.models import Broadcast, AppSetting, User
from app.database.leadership_models import BroadcastAcknowledgement
from app.services.leaders_workspace import verify_member, roster
from app.services.leaders_topics_service import topic_id
from app.services.audit_service import audit
router=Router(name='leaders_broadcast')

class AnnouncementState(StatesGroup):
    text=State()
    confirm=State()


def kb(rows):
    return Markup(inline_keyboard=[[Button(text=t,callback_data=d) for t,d in row] for row in rows])


async def permitted(session,user,settings):
    if not user or user.is_blocked or user.is_archived: return False
    row=await session.scalar(select(AppSetting).where(AppSetting.key=='leaders_broadcast_admin_ids'))
    extra=json.loads(row.value) if row else []
    return user.telegram_id in settings.admin_ids or user.id in extra


async def text_and_keyboard(session,broadcast):
    meta=broadcast.audience_filter_json
    read=int(await session.scalar(select(func.count()).select_from(BroadcastAcknowledgement).where(BroadcastAcknowledgement.broadcast_id==broadcast.id)) or 0)
    text=escape(broadcast.text)
    if meta['kind']!='normal': text+='\n\nОзнакомились: '+str(read)+' / '+str(len(meta['recipients']))
    keyboard=kb([[('✅ Ознакомился',f'leaders_broadcast:read:{broadcast.id}')],[('Кто ещё не подтвердил',f'leaders_broadcast:pending:{broadcast.id}')]]) if meta['kind']!='normal' else None
    return text,keyboard


@router.message(AnnouncementState.text,F.chat.type.in_({'group','supergroup'}))
async def announcement_text(message,state,user,settings,session):
    if message.chat.id!=settings.leaders_chat_id or not await permitted(session,user,settings): return
    value=(message.text or '').strip()
    if not value or len(value)>2800: await message.answer('Отправьте текст до 2800 символов.'); return
    recipients=await roster(session,settings.leaders_chat_id)
    b=Broadcast(title=value[:100],text=value,audience_type='leaders',author_id=user.id,status='draft',
        audience_filter_json={'kind':'important','recipients':[u.id for u in recipients],'chat_id':settings.leaders_chat_id})
    session.add(b);await session.flush()
    await state.set_state(AnnouncementState.confirm)
    await message.answer(f'Оповещение для ЛИДЕРОВ\n\n{value}\n\nПолучателей: {len(recipients)}. Выберите способ отправки.',reply_markup=kb([
        [('Обычное',f'leaders_broadcast:normal:{b.id}')],
        [('📢 Важное + упоминания',f'leaders_broadcast:important:{b.id}')],
        [('🚨 Срочное + личные сообщения',f'leaders_broadcast:urgent:{b.id}')],
        [('Отмена',f'leaders_broadcast:cancel:{b.id}')]]))


@router.callback_query(F.data.startswith('leaders_broadcast:'))
async def announcement_action(call,state,user,settings,session,bot):
    await call.answer()
    if not call.message or call.message.chat.id!=settings.leaders_chat_id or not user: return
    parts=call.data.split(':');action=parts[1]
    try:
        if not await verify_member(session,bot,settings,user): return
        if action=='new':
            if not await permitted(session,user,settings): await call.message.answer('Оповещать всех могут председатель и назначенные им администраторы.');return
            await state.set_state(AnnouncementState.text);await call.message.answer('Напишите сообщение для всей команды. Перед отправкой будет подтверждение.');return
        b=await session.scalar(select(Broadcast).where(Broadcast.id==int(parts[2]),Broadcast.audience_type=='leaders').with_for_update())
        if not b or b.audience_filter_json.get('chat_id')!=settings.leaders_chat_id: return
        meta=dict(b.audience_filter_json)
        if action=='read':
            if b.status!='sent' or user.id not in meta['recipients']: return
            previous=await session.scalar(select(BroadcastAcknowledgement).where(BroadcastAcknowledgement.broadcast_id==b.id,BroadcastAcknowledgement.user_id==user.id))
            if not previous: session.add(BroadcastAcknowledgement(broadcast_id=b.id,user_id=user.id,read_at=datetime.now(timezone.utc)))
            await session.flush()
            text,keyboard=await text_and_keyboard(session,b)
            try: await bot.edit_message_text(chat_id=settings.leaders_chat_id,message_id=meta['message_id'],text=text,reply_markup=keyboard,parse_mode='HTML')
            except TelegramAPIError: pass
            return
        if not await permitted(session,user,settings): return
        if action=='pending':
            ids=set((await session.scalars(select(BroadcastAcknowledgement.user_id).where(BroadcastAcknowledgement.broadcast_id==b.id))).all())
            names=[f'{u.first_name} {u.last_name or ""}'.strip() for u in (await session.scalars(select(User).where(User.id.in_(set(meta['recipients'])-ids)))).all()]
            # Only the authorized reviewer receives this list privately.
            try: await bot.send_message(user.telegram_id,'Ещё не подтвердили:\n'+('\n'.join(names) or 'Все подтвердили.'))
            except TelegramAPIError: await call.message.answer('Откройте личный чат с ботом, чтобы получить список.')
            return
        if b.author_id!=user.id or b.status!='draft': return
        if action=='cancel': b.status='cancelled';await state.clear();await call.message.answer('Оповещение отменено.');return
        if action not in {'normal','important','urgent'}: return
        # Refresh recipients before dispatch; departed members must not receive announcements.
        recipients=await roster(session,settings.leaders_chat_id)
        meta.update(kind=action,recipients=[u.id for u in recipients])
        b.audience_filter_json=meta
        thread=await topic_id(session,settings.leaders_chat_id,'important')
        if not thread: await call.message.answer('Раздел Важно ещё не настроен.');return
        b.status='sending';await session.commit()
        text,keyboard=await text_and_keyboard(session,b)
        try:
            sent=await bot.send_message(settings.leaders_chat_id,text,parse_mode='HTML',message_thread_id=thread,reply_markup=keyboard)
        except TelegramAPIError:
            b.status='failed';await session.commit();await call.message.answer('Не удалось отправить. Текст сохранён; автоматических повторных рассылок не будет.');return
        meta['message_id']=sent.message_id;b.audience_filter_json=meta;b.status='sent';b.sent_at=datetime.now(timezone.utc)
        await audit(session,actor_id=user.id,action='leaders.broadcast_sent',entity_type='broadcast',entity_id=b.id,new_value={'kind':action,'count':len(recipients)})
        await session.commit()
        if action!='normal':
            for offset in range(0,len(recipients),12):
                chunk=recipients[offset:offset+12]
                mentions=' · '.join(f'<a href="tg://user?id={u.telegram_id}">{escape(u.first_name)}</a>' for u in chunk)
                try: await bot.send_message(settings.leaders_chat_id,'Команда: '+mentions,parse_mode='HTML',message_thread_id=thread)
                except TelegramAPIError: meta['mentions_incomplete']=True
            if action=='urgent' or meta.get('mentions_incomplete'):
                from app.services.bot_notification_service import send_bot_notification
                for u in recipients:
                    await send_bot_notification(bot,u.telegram_id,title='Важное сообщение ЭРА',body=b.text,settings=settings,
                        delivery_key=f'leaders-broadcast:{b.id}:{u.id}',notification_type='leaders_broadcast')
        b.audience_filter_json=dict(meta)
        await state.clear()
    except TelegramAPIError:
        await call.message.answer('Не удалось проверить доступ к ЛИДЕРАМ. Попробуйте позже.')
