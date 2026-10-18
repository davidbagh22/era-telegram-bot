from __future__ import annotations
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from app.api.deps import get_session, get_settings, get_bot, get_current_user
from app.api.v1.admin_executive_export import require_admin
from app.api.v1.leader import enforce_leader_action_rate_limit
from app.database.models import User, Task, TaskDelivery, TaskSubmission, LeadershipAttentionItem, AuditLog, Broadcast
from app.services import leaders_workspace as service
from app.services import leaders_access_service as access
from app.services import leaders_campaign_service as campaigns
from app.services.leaders_workcenter_service import sync_one_card
router=APIRouter(prefix='/workcenter',tags=['leaders-workcenter'])


@router.get('/scopes')
async def read_scopes(user:User=Depends(get_current_user),session=Depends(get_session),settings=Depends(get_settings)):
    if not access.active(user): raise HTTPException(403,'workcenter_access_required')
    return {'tasks':await access.scope_options(session,user,settings),
            'broadcasts':await access.scope_options(session,user,settings,'broadcasts.create'),
            'executive':await access.executive(session,user,settings)}


async def require_workcenter(user:User=Depends(get_current_user),session=Depends(get_session),settings=Depends(get_settings)):
    if not access.active(user):
        raise HTTPException(403,'workcenter_access_required')
    known={u.id for u in await service.roster(session,settings.leaders_chat_id)}
    if user.id not in known and not await access.executive(session,user,settings):
        raise HTTPException(403,'workcenter_access_required')
    return user


async def require_executive(user:User=Depends(get_current_user),session=Depends(get_session),settings=Depends(get_settings)):
    if not await access.executive(session,user,settings):
        raise HTTPException(403,'executive_access_required')
    return user



@router.post('/public-tasks/publish',dependencies=[Depends(enforce_leader_action_rate_limit)])
async def publish_public_tasks(admin:User=Depends(require_admin),session=Depends(get_session),settings=Depends(get_settings),bot=Depends(get_bot)):
    """One-click launch: seed the 20 public missions and notify the bot audience."""
    from app.services.public_task_catalog_service import publish_catalog
    result = await publish_catalog(session, creator=admin, bot=bot, settings=settings)
    await session.commit()
    return result


@router.post('/book-club/start',dependencies=[Depends(enforce_leader_action_rate_limit)])
async def start_book_club(admin:User=Depends(require_admin),session=Depends(get_session)):
    from app.services.book_club_service import start
    start_date = await start(session, actor=admin)
    await session.commit()
    return {'started': True, 'start_date': start_date.isoformat(), 'days': 48}


@router.get('/book-club/analytics')
async def book_analytics(admin:User=Depends(require_admin),session=Depends(get_session)):
    from sqlalchemy import func
    from app.database.models import AppSetting
    from app.utils.constants import ApplicationStatus
    # Only totals leave the private diary; never send personal answers to admins.
    subscribed = await session.scalar(select(func.count()).select_from(User).where(
        User.book_club_subscribed.is_(True), User.is_blocked.is_(False),
        User.is_archived.is_(False), User.application_status == ApplicationStatus.APPROVED,
    ))
    keys = (await session.scalars(select(AppSetting.key).where(AppSetting.key.like('book-reflection:%')))).all()
    return {'subscribers': subscribed, 'responses': len(keys), 'respondents': len({k.split(':')[1] for k in keys})}


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
async def roster(admin:User=Depends(require_workcenter),session=Depends(get_session),settings=Depends(get_settings)):
    return [{'id':u.id,'name':f'{u.first_name} {u.last_name or ""}'.strip()} for u in await service.roster(session,settings.leaders_chat_id)]


@router.get('/tasks')
async def tasks(admin:User=Depends(require_workcenter),session=Depends(get_session),settings=Depends(get_settings)):
    rows=(await session.scalars(select(Task).join(TaskDelivery,TaskDelivery.task_id==Task.id).where(
        TaskDelivery.chat_key=='leaders',TaskDelivery.chat_id==settings.leaders_chat_id).order_by(Task.id.desc()).limit(300))).unique().all()
    return [await output(session,t,settings) for t in rows if access.in_scope(admin,t.department_id,t.direction_id)
            or admin.id in {t.creator_id,t.assignee_id} or await service.can_manage_task(session,t,admin,settings)]


class CreateTask(BaseModel):
    title:str=Field(min_length=1,max_length=255)
    description:str=Field(default='',max_length=5000)
    assignee_id:int|None=None
    deadline:datetime|None=None
    project_id:int|None=None
    priority:Literal['normal','urgent']='normal'
    department_id:int|None=None
    direction_id:int|None=None
    points:int=Field(default=10,ge=0,le=1000)
    request_key:str|None=Field(default=None,min_length=8,max_length=80)


@router.post('/tasks',dependencies=[Depends(enforce_leader_action_rate_limit)])
async def create(payload:CreateTask,admin:User=Depends(require_workcenter),session=Depends(get_session),settings=Depends(get_settings),bot=Depends(get_bot)):
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


@router.post('/tasks/{task_id}/action',dependencies=[Depends(enforce_leader_action_rate_limit)])
async def action(task_id:int,payload:TaskAction,admin:User=Depends(require_workcenter),session=Depends(get_session),settings=Depends(get_settings),bot=Depends(get_bot)):
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


@router.post('/decisions/{item_id}',dependencies=[Depends(enforce_leader_action_rate_limit)])
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


@router.get('/team')
async def read_team(q:str='',page:int=0,candidates:bool=False,admin:User=Depends(require_executive),
                    session=Depends(get_session),settings=Depends(get_settings)):
    rows=await access.team(session,settings.leaders_chat_id,query=q,offset=max(0,page)*12,limit=13,candidates=candidates)
    result=[]
    for user in rows[:12]:
        offices=await access.active_office_assignments(session,user.id)
        result.append({'id':user.id,'name':f'{user.first_name} {user.last_name or ""}'.strip(),
            'role':user.role,'offices':[o.title for _,o in offices],
            'can_set_leader':user.role in {'participant','activist','leader'}})
    return {'items':result,'has_more':len(rows)>12}


class SetLeader(BaseModel):
    enabled:bool
    expected_role:str=Field(max_length=32)


@router.post('/team/{user_id}/leader',dependencies=[Depends(enforce_leader_action_rate_limit)])
async def assign_leader(user_id:int,payload:SetLeader,admin:User=Depends(require_executive),
                        session=Depends(get_session),settings=Depends(get_settings)):
    try:
        target=await access.set_leader(session,settings,admin,user_id,**payload.model_dump())
        await session.commit()
        return {'id':target.id,'role':target.role}
    except PermissionError as exc: raise HTTPException(403,str(exc)) from exc
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc


class CampaignInput(BaseModel):
    body:str=Field(min_length=1,max_length=2800)
    request_key:str=Field(min_length=8,max_length=80)
    mode:Literal['group','dm','both']='group'
    department_id:int|None=None
    direction_id:int|None=None
    acknowledge:bool=False


@router.post('/campaigns/preview',dependencies=[Depends(enforce_leader_action_rate_limit)])
async def preview_campaign(payload:CampaignInput,admin:User=Depends(require_workcenter),session=Depends(get_session),settings=Depends(get_settings)):
    try:
        users=await campaigns.recipients(session,settings,admin,payload.department_id,payload.direction_id)
        return {'recipients':len(users),'mode':payload.mode}
    except PermissionError as exc: raise HTTPException(403,str(exc)) from exc


@router.post('/campaigns',dependencies=[Depends(enforce_leader_action_rate_limit)])
async def create_campaign(payload:CampaignInput,admin:User=Depends(require_workcenter),session=Depends(get_session),settings=Depends(get_settings),bot=Depends(get_bot)):
    if not bot: raise HTTPException(503,'bot_unavailable')
    try:
        item=await campaigns.create(session,settings,admin,**payload.model_dump())
        await session.commit()
        await campaigns.send(session,settings,bot,item)
        return await campaigns.summary(session,item)
    except PermissionError as exc: raise HTTPException(403,str(exc)) from exc
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc


@router.get('/campaigns')
async def read_campaigns(admin:User=Depends(require_workcenter),session=Depends(get_session),settings=Depends(get_settings)):
    stmt=select(Broadcast).where(Broadcast.audience_type=='leaders')
    if not await access.executive(session,admin,settings): stmt=stmt.where(Broadcast.author_id==admin.id)
    items=(await session.scalars(stmt.order_by(Broadcast.id.desc()).limit(30))).all()
    return [await campaigns.summary(session,i) for i in items]


class CampaignAction(BaseModel):
    action:Literal['pause','resume','cancel']


@router.post('/campaigns/{item_id}/action',dependencies=[Depends(enforce_leader_action_rate_limit)])
async def campaign_action(item_id:int,payload:CampaignAction,admin:User=Depends(require_workcenter),session=Depends(get_session),settings=Depends(get_settings)):
    from app.services.admin_broadcast_service import BroadcastError
    try:
        item=await campaigns.control(session,settings,admin,item_id,payload.action)
        await session.commit()
        return await campaigns.summary(session,item)
    except PermissionError as exc: raise HTTPException(403,str(exc)) from exc
    except (ValueError,BroadcastError) as exc: raise HTTPException(409,str(exc)) from exc
