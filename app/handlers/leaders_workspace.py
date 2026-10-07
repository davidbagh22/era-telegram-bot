"""Chat-first task wizard and operations for the explicitly bound Leaders chat."""
from __future__ import annotations
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from app.database.models import User, Task, TaskDelivery, TaskSubmission
from app.utils.constants import TaskStatus
from app.services import leaders_workspace as service
from app.services.leaders_workcenter_service import render_task_card, sync_one_card

router = Router(name='leaders_workspace')

class Wizard(StatesGroup):
    title = State()
    assignee = State()
    deadline = State()
    confirm = State()
    action = State()


def kb(rows):
    return Markup(inline_keyboard=[[Button(text=text, callback_data=data) for text,data in row] for row in rows])


def cancel_kb():
    return kb([[('Отмена','wc:cancel')]])


async def allowed(event, bot, settings, session, user):
    message = event.message if hasattr(event,'message') else event
    if not message or message.chat.id != settings.leaders_chat_id:
        return False
    try:
        return await service.verify_member(session, bot, settings, user)
    except TelegramAPIError:
        return False


async def ask_assignee(message, state, session, settings, query=''):
    users = await service.roster(session, settings.leaders_chat_id)
    if query:
        users=[u for u in users if query.lower().lstrip('@') in f'{u.first_name} {u.last_name or ""} {u.username or ""}'.lower()]
    rows=[[(f'{u.first_name} {u.last_name or ""}'.strip(),f'wc:assign:{u.id}') ] for u in users[:30]]
    rows += [[('🟢 Оставить свободной','wc:assign:0')],[('Отмена','wc:cancel')]]
    await state.set_state(Wizard.assignee)
    await message.answer('Кому? Отметьте человека через @ или выберите из ЛИДЕРОВ. Для поиска отправьте имя.',reply_markup=kb(rows))


async def ask_deadline(message, state):
    await state.set_state(Wizard.deadline)
    await message.answer('Срок? Быстрые даты — до 23:59 по Еревану.',reply_markup=kb([
        [('Сегодня','wc:due:0'),('Завтра','wc:due:1')],
        [('Через 3 дня','wc:due:3'),('Выбрать дату','wc:due:custom')],
        [('Без срока','wc:due:none'),('Отмена','wc:cancel')]]))


async def preview(message,state,session):
    data=await state.get_data()
    assignee=await session.get(User,data['assignee_id']) if data.get('assignee_id') else None
    label=f'{assignee.first_name} {assignee.last_name or ""}'.strip() if assignee else 'Свободна'
    deadline=datetime.fromisoformat(data['deadline']) if data.get('deadline') else None
    await state.set_state(Wizard.confirm)
    await message.answer(f"Проверьте задачу:\n\n{data['title']}\n\nИсполнитель: {label}\nСрок: {service.deadline_label(deadline)}",reply_markup=kb([
        [('Создать задачу','wc:create')],[('Изменить исполнителя','wc:assignees'),('Изменить срок','wc:due:choose')],[('Отмена','wc:cancel')]]))


async def begin(message,state,user,session,settings,title=''):
    await state.clear()
    await state.update_data(creator_id=user.id,chat_id=message.chat.id,title=title[:2000])
    if title:
        await ask_assignee(message,state,session,settings)
    else:
        await state.set_state(Wizard.title)
        await message.answer('Что нужно сделать?',reply_markup=cancel_kb())


@router.message(Command('task'), F.chat.type.in_({'group','supergroup'}))
async def start_task(message,state,user,settings,session,bot):
    if not await allowed(message,bot,settings,session,user):
        return
    if not service.manager(user,settings):
        await message.reply('Создавать задачи могут руководители.')
        return
    source=message.reply_to_message
    await begin(message,state,user,session,settings,(source.text or source.caption or '') if source else '')


@router.message(Wizard.title, F.chat.type.in_({'group','supergroup'}))
async def task_title(message,state,user,settings,session,bot):
    if not await allowed(message,bot,settings,session,user) or not service.manager(user,settings):
        return
    title=(message.text or message.caption or '').strip()
    if not title or len(title)>2000:
        await message.reply('Опишите задачу текстом до 2000 символов.')
        return
    await state.update_data(title=title)
    await ask_assignee(message,state,session,settings)


@router.message(Wizard.assignee,F.chat.type.in_({'group','supergroup'}))
async def task_assignee(message,state,user,settings,session,bot):
    if not await allowed(message,bot,settings,session,user) or not service.manager(user,settings):
        return
    ids=[e.user.id for e in message.entities or [] if e.type=='text_mention' and e.user]
    mentions=[e.extract_from(message.text) for e in message.entities or [] if e.type=='mention']
    if ids:
        target=await session.scalar(select(User).where(User.telegram_id==ids[0]))
        if target and await service.verify_member(session,bot,settings,target):
            await state.update_data(assignee_id=target.id)
            await ask_deadline(message,state)
            return
    # A mention can bootstrap an existing member not yet in the roster.
    if mentions:
        target=await session.scalar(select(User).where(User.username.ilike(mentions[0].lstrip('@'))))
        if target and await service.verify_member(session,bot,settings,target):
            await state.update_data(assignee_id=target.id)
            await ask_deadline(message,state)
            return
    await ask_assignee(message,state,session,settings,(message.text or '').strip())


async def save_deadline(message,state,session,settings,user,value):
    data=await state.get_data()
    if data.get('edit_task'):
        task=await service.task_by_id(session,data['edit_task'],settings.leaders_chat_id,lock=True)
        if not task: raise ValueError('Задача не найдена.')
        await service.change_task(session,settings,task,user,'deadline',value)
        await state.clear()
        await message.answer('Срок обновлён. Карточка обновится автоматически.')
    else:
        await state.update_data(deadline=value.isoformat() if value else None)
        await preview(message,state,session)


@router.message(Wizard.deadline,F.chat.type.in_({'group','supergroup'}))
async def task_deadline(message,state,user,settings,session,bot):
    if not await allowed(message,bot,settings,session,user): return
    try:
        value=datetime.strptime(message.text or '', '%d.%m.%Y %H:%M').replace(tzinfo=ZoneInfo(settings.timezone))
        if value<=datetime.now(ZoneInfo(settings.timezone)): raise ValueError()
        await save_deadline(message,state,session,settings,user,value)
    except ValueError:
        await message.reply('Укажите будущий срок: ДД.ММ.ГГГГ ЧЧ:ММ.')


async def details(message,session,task):
    assignee=await session.get(User,task.assignee_id) if task.assignee_id else None
    await message.answer(render_task_card(task,assignee)+'\n\n'+escape(task.description[:1500]),parse_mode='HTML')
    submissions=(await session.scalars(select(TaskSubmission).where(TaskSubmission.task_id==task.id).order_by(TaskSubmission.id.desc()).limit(3))).all()
    for sub in submissions:
        await message.answer(f'Результат: {sub.text or "Вложение"}')
        if sub.file_id:
            try: await message.answer_document(sub.file_id)
            except TelegramAPIError:
                try: await message.answer_photo(sub.file_id)
                except TelegramAPIError: await message.answer('Не удалось загрузить вложение. Оно сохранено у результата.')


@router.callback_query(F.data.startswith('wc:'))
async def workspace_callback(call,state,user,settings,session,bot):
    await call.answer()
    if not await allowed(call,bot,settings,session,user):
        if call.message: await call.message.answer('Нужен подключённый аккаунт участника ЛИДЕРОВ.')
        return
    parts=call.data.split(':'); action=parts[1]
    message=call.message
    try:
        if action=='cancel':
            await state.clear(); await message.answer('Отменено.'); return
        if action=='new':
            if not service.manager(user,settings): raise ValueError('Создавать задачи могут руководители.')
            await begin(message,state,user,session,settings); return
        if action=='list':
            kind=parts[2]
            tasks=list((await session.scalars(select(Task).join(TaskDelivery,TaskDelivery.task_id==Task.id).where(
                TaskDelivery.chat_key=='leaders',TaskDelivery.chat_id==settings.leaders_chat_id).order_by(Task.id.desc()))).unique().all())
            if kind=='mine': tasks=[t for t in tasks if t.assignee_id==user.id and t.status not in service.TERMINAL]
            elif kind=='free': tasks=[t for t in tasks if t.assignee_id is None and t.status not in service.TERMINAL]
            elif kind=='urgent': tasks=[t for t in tasks if service.meta(t).get('priority')=='urgent' and t.status not in service.TERMINAL]
            elif kind=='block': tasks=[t for t in tasks if service.meta(t).get('blocked') and t.status not in service.TERMINAL]
            else: tasks=[t for t in tasks if t.status not in service.TERMINAL]
            await message.answer('Задачи' if tasks else 'Задач в этом списке нет.',reply_markup=kb([[(f'#{t.id} {t.title[:45]}',f'wc:details:{t.id}') ] for t in tasks[:30]]) if tasks else None); return
        if action in {'assignees','assign','due','create'}:
            data=await state.get_data()
            if not service.manager(user,settings) or data.get('creator_id')!=user.id or data.get('chat_id')!=settings.leaders_chat_id:
                raise ValueError('Откройте создание задачи заново.')
            current=await state.get_state()
            if action=='assignees': await ask_assignee(message,state,session,settings); return
            if action=='assign':
                if current!=Wizard.assignee.state: return
                target=int(parts[2]) or None
                if target:
                    member=await session.get(User,target)
                    if not member or not await service.verify_member(session,bot,settings,member): raise ValueError('Человек больше не состоит в ЛИДЕРАХ.')
                if data.get('edit_task'):
                    task=await service.task_by_id(session,data['edit_task'],settings.leaders_chat_id,lock=True)
                    await service.change_task(session,settings,task,user,'assign',target)
                    await state.clear(); await message.answer('Исполнитель изменён.'); return
                await state.update_data(assignee_id=target); await ask_deadline(message,state); return
            if action=='due':
                option=parts[2]
                if option=='choose': await ask_deadline(message,state); return
                if current!=Wizard.deadline.state: return
                if option=='custom': await message.answer('Введите дату: ДД.ММ.ГГГГ ЧЧ:ММ.'); return
                value=None if option=='none' else (datetime.now(ZoneInfo(settings.timezone))+timedelta(days=int(option))).replace(hour=23,minute=59,second=0,microsecond=0)
                await save_deadline(message,state,session,settings,user,value); return
            if current!=Wizard.confirm.state: return
            # Consume confirmation before side effects. Telegram/FSM event isolation serializes a user's callbacks.
            await state.set_state(None)
            task=await service.create_task(session,settings,user,title=data['title'],description=data['title'],
                assignee_id=data.get('assignee_id'),deadline=datetime.fromisoformat(data['deadline']) if data.get('deadline') else None)
            await session.commit()
            await sync_one_card(session,bot,settings,task)
            await session.commit()
            await state.clear()
            await message.answer(f'Задача #{task.id} сохранена.'); return
        task_id=int(parts[2]); task=await service.task_by_id(session,task_id,settings.leaders_chat_id,lock=True)
        if not task: raise ValueError('Задача не найдена.')
        if action=='details': await details(message,session,task); return
        if action=='claim':
            await message.answer('Взять эту задачу на себя?',reply_markup=kb([[('Да, беру',f'wc:take:{task.id}')],[('Отмена','wc:cancel')]])); return
        if action=='take':
            await service.claim_task(session,task,user)
        elif action=='actions':
            rows=[]
            if task.assignee_id==user.id and task.status not in service.TERMINAL:
                rows=[[('Начать',f'wc:start:{task.id}'),('Сдать результат',f'wc:submit:{task.id}')],
                      [('Есть проблема',f'wc:block:{task.id}'),('Вопрос',f'wc:question:{task.id}')],
                      [('Попросить перенос срока',f'wc:extension:{task.id}')]]
            if service.can_manage(task,user,settings) and task.status not in service.TERMINAL:
                rows += [[('Изменить исполнителя',f'wc:reassign:{task.id}'),('Изменить срок',f'wc:reschedule:{task.id}')],
                         [('Срочно',f'wc:urgent:{task.id}'),('Отменить задачу',f'wc:cancel_task:{task.id}')]]
                if task.status==TaskStatus.REVIEW: rows += [[('Принять',f'wc:accept:{task.id}'),('Вернуть',f'wc:return:{task.id}')]]
            if not rows: raise ValueError('Нет доступных действий.')
            await message.answer(f'Действия по задаче #{task.id}',reply_markup=kb(rows)); return
        elif action in {'reassign','reschedule'}:
            if not service.can_manage(task,user,settings): raise ValueError('Нужны права руководителя.')
            await state.clear(); await state.update_data(creator_id=user.id,chat_id=settings.leaders_chat_id,edit_task=task.id)
            if action=='reassign': await ask_assignee(message,state,session,settings)
            else: await ask_deadline(message,state)
            return
        elif action in {'submit','block','question','return','extension'}:
            if action=='return' and not service.can_manage(task,user,settings): raise ValueError('Нужны права руководителя.')
            if action!='return' and task.assignee_id!=user.id: raise ValueError('Действие доступно исполнителю.')
            await state.set_state(Wizard.action); await state.update_data(action=action,task_id=task.id,chat_id=settings.leaders_chat_id)
            prompts={'submit':'Что сделано? Отправьте текст, ссылку, фото или документ.', 'return':'Что нужно исправить?',
                'block':'Что мешает? Вопрос попадёт в решения руководства.','question':'Какой вопрос нужно решить?',
                'extension':'Укажите желаемый срок и причину. Руководитель получит запрос.'}
            await message.answer(prompts[action],reply_markup=cancel_kb()); return
        elif action=='cancel_task':
            if not service.can_manage(task,user,settings): raise ValueError('Нужны права руководителя.')
            await message.answer('Отменить задачу?',reply_markup=kb([[('Да, отменить',f'wc:cancel_confirm:{task.id}')],[('Назад',f'wc:actions:{task.id}')]])); return
        else:
            mapped={'cancel_confirm':'cancel','urgent':'urgent','start':'start','accept':'accept'}.get(action)
            if not mapped: return
            await service.change_task(session,settings,task,user,mapped,True if action=='urgent' else None)
        await session.commit(); await sync_one_card(session,bot,settings,task); await session.commit()
        await message.answer('Сохранено.')
    except (ValueError,TelegramAPIError) as exc:
        await message.answer(str(exc)[:500] if isinstance(exc,ValueError) else 'Telegram временно недоступен. Повторите действие.')


@router.message(Wizard.action,F.chat.type.in_({'group','supergroup'}))
async def task_action_text(message,state,user,settings,session,bot):
    if not await allowed(message,bot,settings,session,user): return
    data=await state.get_data()
    if data.get('chat_id')!=message.chat.id: return
    task=await service.task_by_id(session,data.get('task_id'),settings.leaders_chat_id,lock=True)
    if not task: return
    action=data['action']; text=(message.text or message.caption or '').strip()[:5000]
    attachment=message.document or (message.photo[-1] if message.photo else None)
    if not text and not attachment: await message.reply('Отправьте текст, фото или документ.'); return
    try:
        await service.change_task(session,settings,task,user,'question' if action=='extension' else action,
            (text,attachment.file_id if attachment else None) if action=='submit' else text)
        await session.commit(); await sync_one_card(session,bot,settings,task); await session.commit()
        await state.clear()
        target=await session.get(User,task.assignee_id if action=='return' else task.creator_id)
        if target:
            from app.services.bot_notification_service import send_bot_notification
            await send_bot_notification(bot,target.telegram_id,settings=settings,title=f'Задача #{task.id}',
                body=f'{task.title}\n'+{'submit':'Результат на проверке.','return':'Результат возвращён на доработку.','block':'Нужна помощь.','question':'Поступил вопрос.','extension':'Запрошен перенос срока.'}[action],
                delivery_key=f'leaders-action:{task.id}:{message.chat.id}:{message.message_id}',notification_type='leaders_task')
        await message.reply('Сохранено. Карточка обновлена.')
    except ValueError as exc: await message.reply(str(exc))
