"""Shared Leaders workflows. Task remains the single source of truth."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update, text as sql_text
from app.database.models import Task, TaskDelivery, TaskSubmission, User, LeadershipAttentionItem
from app.services.audit_service import audit
from app.services.weekly_pulse_cycle_service import upsert_leader_membership
from app.utils.constants import Role, TaskStatus
from app.services import leaders_access_service as access

TERMINAL = {TaskStatus.COMPLETED, TaskStatus.CANCELLED}


async def can_create_any(session, user, settings):
    return bool(await access.scopes(session, user, settings))


async def can_manage_task(session, task, user, settings):
    return await access.permitted_scope(session, user, settings,
        department_id=task.department_id, direction_id=task.direction_id)



def meta(task):
    return (task.reward_json or {}).get('leaders', {})


def set_meta(task, **values):
    task.reward_json = {**(task.reward_json or {}), 'leaders': {**meta(task), **values}}


async def roster(session, chat_id):
    return await access.team(session, chat_id, limit=None)


async def verify_member(session, bot, settings, user):
    if not access.active(user) or not settings.leaders_chat_id:
        return False
    if user.role == Role.LEADER or await access.executive(session, user, settings) or await access.scopes(session, user, settings):
        return True
    member = await bot.get_chat_member(settings.leaders_chat_id, user.telegram_id)
    row = await upsert_leader_membership(session, leader_chat_id=settings.leaders_chat_id,
        telegram_user_id=user.telegram_id, membership_status=member.status,
        is_member=getattr(member, 'is_member', None), username=user.username,
        display_name=f'{user.first_name} {user.last_name or ""}'.strip())
    return row.is_weekly_pulse_eligible


async def task_by_id(session, task_id, chat_id, *, lock=False):
    q = select(Task).join(TaskDelivery, TaskDelivery.task_id == Task.id).where(
        Task.id == task_id, TaskDelivery.chat_key == 'leaders', TaskDelivery.chat_id == chat_id)
    if lock:
        q = q.with_for_update(of=Task).execution_options(populate_existing=True)
    return await session.scalar(q)


async def create_task(session, settings, creator, *, title, description='', assignee_id=None,
                      deadline=None, priority='normal', project_id=None, source='telegram', request_key=None,
                      department_id=None, direction_id=None, points=10):
    if not await access.permitted_scope(session, creator, settings, department_id=department_id, direction_id=direction_id):
        raise ValueError('Создавать задачи могут только руководители.')
    if not settings.leaders_chat_id or settings.leaders_chat_id == settings.general_chat_id:
        raise ValueError('Рабочий чат ЛИДЕРЫ не привязан.')
    if not title.strip():
        raise ValueError('Укажите задачу.')
    if assignee_id is not None and assignee_id not in {u.id for u in await roster(session, settings.leaders_chat_id)}:
        raise ValueError('Исполнитель должен состоять в ЛИДЕРАХ и подключить бота.')
    if assignee_id is not None:
        assignee = await session.get(User, assignee_id)
        if not assignee or not await access.user_in_scope(session, assignee, department_id, direction_id):
            raise ValueError('Исполнитель не входит в выбранную команду.')
    if not 0 <= points <= 1000:
        raise ValueError('Баллы должны быть от 0 до 1000.')
    request_hash=None
    if request_key:
        import hashlib, json
        normalized_deadline=(deadline.replace(tzinfo=timezone.utc) if deadline and deadline.tzinfo is None else deadline)
        request_hash=hashlib.sha256(json.dumps([title.strip()[:255],description.strip()[:5000] or title.strip(),assignee_id,
            department_id,direction_id,project_id,priority,points,
            normalized_deadline.astimezone(timezone.utc).isoformat() if normalized_deadline else None],ensure_ascii=False).encode()).hexdigest()
        key = f'{creator.id}:{request_key}'
        if session.bind.dialect.name == 'postgresql':
            lock = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
            await session.execute(sql_text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock})
        old = await session.scalar(select(Task).where(Task.creator_id == creator.id,
            Task.reward_json['leaders']['request_key'].as_string() == request_key))
        if old:
            saved_hash = meta(old).get('request_hash')
            if saved_hash and saved_hash != request_hash:
                raise ValueError('Подтверждение уже использовано для другой задачи.')
            if not saved_hash and (old.title, old.assignee_id, old.department_id, old.direction_id) != (title.strip()[:255], assignee_id, department_id, direction_id):
                raise ValueError('Подтверждение уже использовано для другой задачи.')
            return old
    if deadline:
        if deadline.tzinfo is None:
            raise ValueError('Для срока требуется часовой пояс.')
        if deadline <= datetime.now(timezone.utc):
            raise ValueError('Срок должен быть в будущем.')
    task = Task(title=title.strip()[:255], description=description.strip()[:5000] or title.strip(),
        assignee_id=assignee_id, creator_id=creator.id, deadline=deadline, points=points, department_id=department_id, direction_id=direction_id,
        task_type='private', project_id=project_id,
        remind_at=deadline-timedelta(hours=24) if deadline else None)
    set_meta(task, priority=priority, created_via=source, request_key=request_key, request_hash=request_hash, accepted=False if assignee_id else None)
    session.add(task)
    await session.flush()
    from app.services.leaders_topics_service import topic_id
    session.add(TaskDelivery(task_id=task.id, chat_key='leaders', chat_id=settings.leaders_chat_id,
        message_thread_id=await topic_id(session, settings.leaders_chat_id, 'tasks'),
        status='pending', remind_at=task.remind_at))
    await audit(session, actor_id=creator.id, action='leaders.task_created', entity_type='task',
                entity_id=task.id, new_value={'created_via':source,'assignee_id':assignee_id})
    return task


async def claim_task(session, task, user):
    if not access.active(user) or not await access.user_in_scope(session, user, task.department_id, task.direction_id):
        raise ValueError('Эта задача доступна другой команде.')
    result = await session.execute(update(Task).where(Task.id == task.id,
        Task.assignee_id.is_(None), Task.status.in_([TaskStatus.NEW, TaskStatus.PUBLISHED]))
        .values(assignee_id=user.id).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise ValueError('Задачу уже взял другой участник.')
    await session.refresh(task)
    set_meta(task, accepted=True)
    await audit(session, actor_id=user.id, action='leaders.task_claimed', entity_type='task', entity_id=task.id)


async def change_task(session, settings, task, user, action, value=None):
    if not access.active(user):
        raise ValueError('Доступ отозван.')
    if task.status in TERMINAL:
        raise ValueError('Задача уже закрыта.')
    if action in {'start','block','submit','question','decline'}:
        if task.assignee_id != user.id:
            raise ValueError('Действие доступно исполнителю.')
    elif not await can_manage_task(session, task, user, settings):
        raise ValueError('Действие доступно автору и руководству.')
    old = {'status':str(task.status), 'assignee_id':task.assignee_id,
           'deadline':(task.deadline.isoformat() if task.deadline else "") if task.deadline else None}
    if action == 'decline':
        if task.status not in {TaskStatus.NEW, TaskStatus.PUBLISHED} or meta(task).get('accepted'):
            raise ValueError('Начатую задачу можно передать через руководителя.')
        task.assignee_id = None
        set_meta(task, accepted=None)
    elif action == 'start':
        if task.status not in {TaskStatus.NEW, TaskStatus.PUBLISHED, TaskStatus.OVERDUE}:
            raise ValueError('Задача уже начата.')
        task.status = TaskStatus.IN_PROGRESS
        set_meta(task, accepted=True)
    elif action == 'assign':
        if value is not None and value not in {u.id for u in await roster(session, settings.leaders_chat_id)}:
            raise ValueError('Исполнитель не состоит в ЛИДЕРАХ.')
        if task.status == TaskStatus.REVIEW:
            raise ValueError('Сначала примите или верните текущий результат.')
        target = await session.get(User, value) if value else None
        if target and not await access.user_in_scope(session, target, task.department_id, task.direction_id):
            raise ValueError('Исполнитель не входит в выбранную команду.')
        task.assignee_id = value
        set_meta(task, accepted=False if value else None)
    elif action == 'deadline':
        if value is not None and (value.tzinfo is None or value <= datetime.now(timezone.utc)):
            raise ValueError('Укажите будущий срок с часовым поясом.')
        if task.status == TaskStatus.OVERDUE and value is not None:
            pending = await session.scalar(select(TaskSubmission.id).where(TaskSubmission.task_id == task.id, TaskSubmission.status == 'pending').limit(1))
            task.status = TaskStatus.REVIEW if pending else TaskStatus.IN_PROGRESS
        task.deadline = value
        task.remind_at = value-timedelta(hours=24) if value else None
        for delivery in (await session.scalars(select(TaskDelivery).where(TaskDelivery.task_id == task.id))).all():
            delivery.remind_at = task.remind_at
            delivery.reminder_count = 0
    elif action == 'urgent':
        set_meta(task, priority='urgent' if value else 'normal')
    elif action == 'cancel':
        task.status = TaskStatus.CANCELLED
    elif action in {'block','question'}:
        task.comment = str(value).strip()[:2000]
        set_meta(task, blocked=action == 'block')
        item = await session.scalar(select(LeadershipAttentionItem).where(
            LeadershipAttentionItem.type == 'leaders_task', LeadershipAttentionItem.scope_id == task.id,
            LeadershipAttentionItem.status.in_(['open','in_progress'])))
        if item is None:
            item = LeadershipAttentionItem(type='leaders_task', scope_type='task', scope_id=task.id,
                owner_id=user.id, responsible_id=task.creator_id, severity='high', status='open')
            session.add(item)
        item.resolution = task.comment
    elif action == 'submit':
        if task.status == TaskStatus.REVIEW:
            raise ValueError('Результат уже ожидает проверки.')
        text, file_id = value
        if not text and not file_id:
            raise ValueError('Добавьте текст, ссылку, файл или фото.')
        session.add(TaskSubmission(task_id=task.id, user_id=user.id, text=text, file_id=file_id, status='pending'))
        task.status = TaskStatus.REVIEW
        set_meta(task, blocked=False)
    elif action in {'accept','return'}:
        if task.assignee_id == user.id:
            raise ValueError('Результат должен проверить другой руководитель.')
        if action == 'return' and not str(value or '').strip():
            raise ValueError('Укажите, что требуется исправить.')
        submission = await session.scalar(select(TaskSubmission).where(TaskSubmission.task_id == task.id,
            TaskSubmission.status == 'pending').order_by(TaskSubmission.id.desc()).with_for_update())
        if submission is None or task.status != TaskStatus.REVIEW:
            raise ValueError('Нет результата на проверке.')
        from app.services.task_review_service import decide_submission
        assignee = await session.get(User, submission.user_id)
        await decide_submission(session, submission, task, assignee,
            action='approve' if action == 'accept' else 'revision', comment=value or '', actor=user)
        if action == 'accept':
            task.status = TaskStatus.COMPLETED
            set_meta(task, completed_at=datetime.now(timezone.utc).isoformat(), blocked=False)
    else:
        raise ValueError('Неизвестное действие.')
    await audit(session, actor_id=user.id, action=f'leaders.task_{action}', entity_type='task',
                entity_id=task.id, old_value=old, new_value={'status':str(task.status), 'assignee_id':task.assignee_id,
                    'deadline':task.deadline.isoformat() if task.deadline else None})


def deadline_label(value, fmt='%d.%m.%Y %H:%M'):
    from zoneinfo import ZoneInfo
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(ZoneInfo('Asia/Yerevan')).strftime(fmt) if value else 'Без срока'
