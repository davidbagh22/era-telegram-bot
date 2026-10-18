"""Native entry points; task mutations remain in the shared workcenter service."""
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from app.database.models import Broadcast, User
from app.handlers.leaders_workspace import Wizard, allowed, kb, workspace_callback
from app.services import leaders_access_service as access
from app.services import leaders_campaign_service as campaigns

router = Router(name='leaders_native')


class TeamState(StatesGroup):
    search = State()


class CampaignState(StatesGroup):
    text = State()
    confirm = State()


@router.message(Command('cancel'), StateFilter(TeamState.search, CampaignState.text, CampaignState.confirm,
    Wizard.title, Wizard.assignee, Wizard.deadline, Wizard.confirm, Wizard.action))
async def cancel_native_flow(message, state):
    await state.clear()
    await message.answer('Действие отменено. Откройте /leaders для продолжения.')


async def show_home(message, session, settings, user):
    rows = [[('Мои задачи','wc:list:mine'),('Свободные','wc:list:free')],
            [('Завершённые','wc:list:completed')]]
    if await access.scopes(session,user,settings):
        rows.insert(0,[('➕ Новая задача','wc:new'),('На проверке','wc:list:review')])
    if await access.scopes(session,user,settings,'broadcasts.create'):
        rows.append([('📢 Новая рассылка','lc:new'),('История рассылок','lc:history')])
    if await access.executive(session,user,settings):
        rows.append([('👥 Команда и лидеры','leaders_team:list:0')])
    rows.append([('← Главное меню','home')])
    await message.answer('🧭 Лидеры ЭРА\n\nЗадачи, результаты и сообщения команды. Пульс недели доступен по /pulse.',reply_markup=kb(rows))


@router.message(Command('leader','leaders'),F.chat.type=='private')
@router.message(CommandStart(deep_link=True,magic=F.args=='leaders'),F.chat.type=='private')
@router.message(F.text.in_({'🧭 Панель лидера','🧭 Лидеры','Лидеры'}),F.chat.type=='private')
async def native_leaders(message,state,user,settings,session,bot):
    if not await allowed(message,bot,settings,session,user):
        await message.answer('Рабочий центр доступен участникам площадки лидеров. Для подключения аккаунта начните с /start.')
        return
    await state.clear()
    await show_home(message,session,settings,user)


@router.callback_query(F.data.in_({'wc:home','leader:panel'}))
async def native_home(call,state,user,settings,session,bot):
    await call.answer()
    if not await allowed(call,bot,settings,session,user):
        return
    await state.clear()
    if getattr(call.message.chat,'type',None)!='private':
        me=await bot.get_me()
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        await call.message.answer('Личные действия доступны в боте.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text='Открыть Лидеры',url=f'https://t.me/{me.username}?start=leaders')]]))
        return
    await show_home(call.message,session,settings,user)


@router.callback_query(F.data=='leader:task:new')
async def old_task_entry(call,state,user,settings,session,bot):
    await workspace_callback(call.model_copy(update={'data':'wc:new'}),state,user,settings,session,bot)


async def show_team(message,session,settings,*,page=0,query='',candidates=False):
    people=await access.team(session,settings.leaders_chat_id,query=query,offset=page*8,limit=9,candidates=candidates)
    rows=[[(f'{p.first_name} {p.last_name or ""}'.strip()[:40]+' · '+{'leader':'Лидер','head':'Руководитель','admin':'Админ'}.get(p.role,'Участник'),
            f'leaders_team:item:{p.id}')] for p in people[:8]]
    nav=[]
    if page: nav.append(('←',f'leaders_team:list:{page-1}'))
    if len(people)>8 and not candidates: nav.append(('→',f'leaders_team:list:{page+1}'))
    if nav: rows.append(nav)
    rows += [[('Найти / назначить лидера','leaders_team:search')],[('← Лидеры','wc:home')]]
    await message.answer('👥 Команда ЭРА\n\nСтатус лидера не даёт права управлять всей командой. Должности и полномочия учитываются отдельно.',reply_markup=kb(rows))


@router.callback_query(F.data.startswith('leaders_team:'),F.message.chat.type=='private')
async def team_callback(call,state,user,settings,session):
    await call.answer()
    if not await access.executive(session,user,settings):
        await call.message.answer('Назначать лидеров могут председатель и заместитель.')
        return
    parts=call.data.split(':')
    action=parts[1]
    if action=='search':
        await state.set_state(TeamState.search)
        await call.message.answer('Отправьте имя, @username или Telegram ID. /cancel — отменить.')
        return
    if action=='list':
        await state.clear()
        await show_team(call.message,session,settings,page=max(0,int(parts[2])))
        return
    target=await session.get(User,int(parts[2]))
    if not target:
        return
    if action=='set':
        try:
            await access.set_leader(session,settings,user,target.id,enabled=parts[3]=='1',expected_role=parts[4])
            await session.commit()
            await state.clear()
            await call.message.answer('Статус обновлён. Баллы и история сохранены.')
        except (ValueError,PermissionError) as exc:
            await session.rollback()
            await call.message.answer(str(exc))
        return
    rows=[]
    if target.role in {'participant','activist','leader'}:
        enabled=target.role!='leader'
        rows.append([('Подтвердить назначение лидером' if enabled else 'Снять статус лидера',
                      f'leaders_team:set:{target.id}:{int(enabled)}:{target.role}')])
    rows.append([('← Команда','leaders_team:list:0')])
    offices=await access.active_office_assignments(session,target.id)
    await call.message.answer(f'{target.first_name} {target.last_name or ""}\n'
        f'Роль: { {"participant":"Участник","activist":"Активист","leader":"Лидер","head":"Руководитель","admin":"Администратор"}.get(target.role,target.role)}\n'
        'Должности: '+(', '.join(o.title for _,o in offices) or 'не назначены')+
        '\n\nНазначение лидером не выдаёт права рассылать всем, проверять чужие результаты или назначать должности.',reply_markup=kb(rows))


@router.message(TeamState.search,F.chat.type=='private',~F.text.startswith('/'))
async def team_search(message,state,user,settings,session):
    if not await access.executive(session,user,settings):
        await state.clear()
        return
    await show_team(message,session,settings,query=message.text or '',candidates=True)


@router.callback_query(F.data.regexp(r'^lc:(new|history|scope|mode|send|cancel|view|pause|resume|stop)(:.*)?$'))
async def campaign_callback(call,state,user,settings,session,bot):
    await call.answer()
    if not await allowed(call,bot,settings,session,user):
        return
    parts=call.data.split(':'); action=parts[1]
    try:
        options=await access.scope_options(session,user,settings,'broadcasts.create')
        if not options:
            raise PermissionError('Нет права создавать рассылки.')
        if action=='new':
            await state.clear()
            await state.set_state(CampaignState.text)
            await state.update_data(owner_id=user.id,chat_id=call.message.chat.id,request_key=str(uuid4()))
            await call.message.answer('Напишите сообщение для команды до 2800 символов. Перед отправкой будет предпросмотр.')
        elif action=='cancel':
            await state.clear()
            await call.message.answer('Отменено.')
        elif action=='scope':
            data=await state.get_data()
            if data.get('owner_id')!=user.id or data.get('chat_id')!=call.message.chat.id or await state.get_state()!=CampaignState.confirm.state:
                raise ValueError('Откройте рассылку заново.')
            scope=next((o for o in options if o['kind']==parts[2] and o['id']==int(parts[3])),None)
            if not scope: raise PermissionError('Нет доступа к этой команде.')
            dept=scope['id'] if scope['kind']=='department' else None
            direction=scope['id'] if scope['kind']=='direction' else None
            people=await campaigns.recipients(session,settings,user,dept,direction)
            await state.update_data(department_id=dept,direction_id=direction)
            modes=[('Лично','dm')] if dept or direction else [('В чат','group'),('Лично','dm'),('В чат и лично','both')]
            await call.message.answer(f'Проверьте рассылку\n\n{data["body"]}\n\nКоманда: {scope["name"]}\n'
                f'Известных доступных аккаунтов: {len(people)}. Доставка будет отражена отдельно.\n'
                'Нажатие следующей кнопки подтвердит отправку.',reply_markup=kb(
                    [[(label,f'lc:send:{mode}')] for label,mode in modes]+[[('Отмена','lc:cancel')]]))
        elif action=='send':
            data=await state.get_data()
            if data.get('owner_id')!=user.id or data.get('chat_id')!=call.message.chat.id or await state.get_state()!=CampaignState.confirm.state:
                raise ValueError('Подтверждение уже принято или устарело.')
            item=await campaigns.create(session,settings,user,body=data['body'],request_key=data['request_key'],mode=parts[2],
                department_id=data.get('department_id'),direction_id=data.get('direction_id'),acknowledge=True)
            await session.commit()
            await state.clear()
            await campaigns.send(session,settings,bot,item)
            await show_campaign(call.message,session,item)
        elif action=='history':
            items=(await session.scalars(select(Broadcast).where(Broadcast.audience_type=='leaders').order_by(Broadcast.id.desc()).limit(12))).all()
            if not await access.executive(session,user,settings): items=[i for i in items if i.author_id==user.id]
            await call.message.answer('Рассылки команды',reply_markup=kb([[(f'#{i.id} · {i.title[:40]}',f'lc:view:{i.id}')] for i in items]+[[('← Лидеры','wc:home')]]))
        elif action in {'view','pause','resume','stop'}:
            item=await session.get(Broadcast,int(parts[2]))
            if not item or item.audience_type!='leaders': raise ValueError('Рассылка недоступна.')
            if item.author_id!=user.id and not await access.executive(session,user,settings): raise PermissionError('Рассылка другой команды.')
            if action!='view':
                await campaigns.control(session,settings,user,item.id,'cancel' if action=='stop' else action)
                await session.commit()
            await show_campaign(call.message,session,item)
    except (ValueError,PermissionError) as exc:
        await session.rollback()
        await call.message.answer(str(exc))


@router.message(CampaignState.text,~F.text.startswith('/'))
async def campaign_text(message,state,user,settings,session,bot):
    data=await state.get_data()
    if not await allowed(message,bot,settings,session,user) or data.get('owner_id')!=user.id or data.get('chat_id')!=message.chat.id:
        return
    body=(message.text or '').strip()
    if not body or len(body)>2800 or body.startswith('/'):
        await message.answer('Нужен текст до 2800 символов или /cancel.')
        return
    options=await access.scope_options(session,user,settings,'broadcasts.create')
    await state.update_data(body=body)
    await state.set_state(CampaignState.confirm)
    await message.answer('Кому отправить?',reply_markup=kb([[(o['name'],f'lc:scope:{o["kind"]}:{o["id"]}')] for o in options]))


async def show_campaign(message,session,item):
    data=await campaigns.summary(session,item)
    rows=[]
    if item.status=='sending': rows.append([('Пауза',f'lc:pause:{item.id}')])
    if item.status=='paused': rows.append([('Продолжить',f'lc:resume:{item.id}')])
    if item.status in {'sending','paused'}: rows.append([('Отменить оставшиеся',f'lc:stop:{item.id}')])
    rows += [[('Обновить',f'lc:view:{item.id}'),('← Лидеры','wc:home')]]
    label={'sending':'Отправляется','paused':'На паузе','sent':'Передано Telegram','cancelled':'Отменена',
           'partial':'Часть адресатов недоступна','review_required':'Нужна сверка доставки'}.get(item.status,item.status)
    await message.answer(f'Рассылка #{item.id} · {label}\nВыбрано аккаунтов: {data["recipients"]}\n'
        f'Отправок подтверждено: {data["sent"]}\nНедоступны: {data["unreachable"]}\n'
        f'Исход неизвестен: {data["uncertain"]}\nОзнакомились: {data["read"]}',reply_markup=kb(rows))
