from __future__ import annotations
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from app.api.deps import get_session, get_settings, get_current_user, get_bot
from app.api.v1.admin_executive_export import require_admin
from app.database.models import User, Task, TaskDelivery, TaskSubmission, LeadershipAttentionItem, AuditLog, Broadcast
from app.services import leaders_workspace as service
from app.services.leaders_workcenter_service import sync_one_card
router=APIRouter(prefix='/workcenter',tags=['leaders-workcenter'])


@router.post('/public-tasks/publish')
async def publish_public_tasks(admin:User=Depends(require_admin),session=Depends(get_session),settings=Depends(get_settings),bot=Depends(get_bot)):
    """One-click launch: seed the 20 public missions and notify the bot audience."""
    from app.services.public_task_catalog_service import publish_catalog
    result = await publish_catalog(session, creator=admin, bot=bot, settings=settings)
    await session.commit()
    return result


@router.post('/book-club/start')
async def start_book_club(admin:User=Depends(require_admin),session=Depends(get_session)):
    from app.services.book_club_service import start
    start_date = await start(session, actor=admin)
    await session.commit()
    return {'started': True, 'start_date': start_date.isoformat(), 'days': 48}


async def output(session,task,settings):
    delivery=await session.scalar(select(TaskDelivery).where(TaskDelivery.task_id==task.id,TaskDelivery.chat_key=='leaders'))
    user=await session.get(User,task.assignee_id) if task.assignee_id else None
    submissions=(await session.scalars(select(TaskSubmission).where(TaskSubmission.task_id==task.id).order_by(TaskSubmission.id.desc()))).all()
    history=(await session.scalars(select(AuditLog).where(AuditLog.entity_type=='task',AuditLog.entity_id==task.id).order_by(AuditLog.id.desc()).limit(30))).all()
    url=None
    if delivery and delivery.telegram_message_id and str(delivery.chat_id).startswith('-100'):
        url=f'https://t.me/c/{str(delivery.chat_id)[4:]}/{delivery.telegram_message_id}'
    return {'id':task.id,'title':task.title,'description':task.description,'assignee_id':task.assignee_id,
        'assignee_name':f'{user.first_name} {user.last_name or ""}'.strip() if user else 'Свободна',
        'creator_id':task.creator_id,'deadline':task.deadline.isoformat() if task.deadline else None,
        'status':task.status,'priority':service.meta(task).get('priority','normal'),
        'project_id':task.project_id,'blocker':task.comment if service.meta(task).get('blocked') else None,
        'telegram_url':url,'delivery_status':delivery.status if delivery else None,
        'submissions':[{'id':s.id,'text':s.text,'has_file':bool(s.file_id),'status':s.status,'comment':s.admin_comment} for s in submissions],
        'history':[{'action':h.action,'at':h.created_at.isoformat()} for h in history]}


@router.get('/roster')
async def roster(admin:User=Depends(require_admin),session=Depends(get_session),settings=Depends(get_settings)):
    return [{'id':u.id,'name':f'{u.first_name} {u.last_name or ""}'.strip()} for u in await service.roster(session,settings.leaders_chat_id)]


@router.get('/tasks')
async def tasks(admin:User=Depends(require_admin),session=Depends(get_session),settings=Depends(get_settings)):
    rows=(await session.scalars(select(Task).join(TaskDelivery,TaskDelivery.task_id==Task.id).where(
        TaskDelivery.chat_key=='leaders',TaskDelivery.chat_id==settings.leaders_chat_id).order_by(Task.id.desc()).limit(300))).unique().all()
    return [await output(session,t,settings) for t in rows]


class CreateTask(BaseModel):
    title:str=Field(min_length=1,max_length=255)
    description:str=Field(default='',max_length=5000)
    assignee_id:int|None=None
    deadline:datetime|None=None
    project_id:int|None=None
    priority:Literal['normal','urgent']='normal'


@router.post('/tasks')
async def create(payload:CreateTask,admin:User=Depends(require_admin),session=Depends(get_session),settings=Depends(get_settings),bot=Depends(get_bot)):
    try:
        if payload.assignee_id:
            assignee=await session.get(User,payload.assignee_id)
            if bot and not await service.verify_member(session,bot,settings,assignee):
                raise ValueError('Исполнитель не состоит в ЛИДЕРАХ.')
        task=await service.create_task(session,settings,admin,**payload.model_dump(),source='admin')
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    await session.commit()
    if bot: await sync_one_card(session,bot,settings,task);await session.commit()
    return await output(session,task,settings)


class TaskAction(BaseModel):
    action:Literal['assign','deadline','urgent','cancel','accept','return']
    assignee_id:int|None=None
    deadline:datetime|None=None
    comment:str=Field(default='',max_length=2000)
    urgent:bool=True


@router.post('/tasks/{task_id}/action')
async def action(task_id:int,payload:TaskAction,admin:User=Depends(require_admin),session=Depends(get_session),settings=Depends(get_settings),bot=Depends(get_bot)):
    task=await service.task_by_id(session,task_id,settings.leaders_chat_id,lock=True)
    if not task: raise HTTPException(404,'task_not_found')
    value={'assign':payload.assignee_id,'deadline':payload.deadline,'urgent':payload.urgent,'return':payload.comment}.get(payload.action)
    if payload.action=='deadline' and value and (value.tzinfo is None or value.timestamp()<=datetime.now().timestamp()):
        raise HTTPException(422,'Укажите будущую дату с часовым поясом.')
    try: await service.change_task(session,settings,task,admin,payload.action,value)
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    await session.commit()
    if bot: await sync_one_card(session,bot,settings,task);await session.commit()
    return await output(session,task,settings)


@router.get('/decisions')
async def decisions(admin:User=Depends(require_admin),session=Depends(get_session)):
    items=(await session.scalars(select(LeadershipAttentionItem).order_by(LeadershipAttentionItem.created_at.desc()).limit(200))).all()
    return [{'id':i.id,'type':i.type,'owner_id':i.owner_id,'responsible_id':i.responsible_id,'status':i.status,
        'text':i.resolution or 'Запрос требует внимания','task_id':i.scope_id if i.scope_type=='task' else None} for i in items]


class DecisionAction(BaseModel):
    status:Literal['open','in_progress','resolved','deferred']
    responsible_id:int|None=None
    comment:str=Field(default='',max_length=2000)


@router.post('/decisions/{item_id}')
async def decide(item_id:int,payload:DecisionAction,admin:User=Depends(require_admin),session=Depends(get_session),settings=Depends(get_settings),bot=Depends(get_bot)):
    from datetime import timezone
    from app.services.audit_service import audit
    item=await session.get(LeadershipAttentionItem,item_id)
    if not item: raise HTTPException(404,'decision_not_found')
    if payload.responsible_id and not await session.get(User,payload.responsible_id): raise HTTPException(422,'user_not_found')
    old={'status':item.status,'responsible_id':item.responsible_id}
    item.status=payload.status;item.responsible_id=payload.responsible_id
    item.resolved_at=datetime.now(timezone.utc) if payload.status=='resolved' else None
    if payload.comment: item.resolution=(item.resolution or '')+'\nРешение: '+payload.comment
    await audit(session,actor_id=admin.id,action='leaders.decision_updated',entity_type='leadership_attention_item',entity_id=item.id,old_value=old,new_value=payload.model_dump())
    await session.commit()
    owner=await session.get(User,item.owner_id) if item.owner_id else None
    if bot and owner:
        from app.services.bot_notification_service import send_bot_notification
        await send_bot_notification(bot,owner.telegram_id,title='По вашему вопросу есть решение',body=payload.comment or payload.status,
            settings=settings,delivery_key=f'decision:{item.id}:{item.updated_at.isoformat()}',notification_type='leaders_decision')
    return {'id':item.id,'status':item.status}


@router.get('/announcements')
async def announcements(admin:User=Depends(require_admin),session=Depends(get_session)):
    from app.database.leadership_models import BroadcastAcknowledgement
    items=(await session.scalars(select(Broadcast).where(Broadcast.audience_type=='leaders').order_by(Broadcast.id.desc()).limit(50))).all()
    return [{'id':i.id,'text':i.text,'status':i.status,'kind':i.audience_filter_json.get('kind'),
        'recipients':len(i.audience_filter_json.get('recipients',[])),
        'read':len((await session.scalars(select(BroadcastAcknowledgement.id).where(BroadcastAcknowledgement.broadcast_id==i.id))).all())} for i in items]
