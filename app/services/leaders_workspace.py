"""Shared Leaders workflows. Task remains the single source of truth."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from html import escape
from sqlalchemy import select, update
from app.database.models import Task, TaskDelivery, TaskSubmission, User, LeadershipAttentionItem
from app.database.leadership_models import LeaderChatMembership
from app.services.audit_service import audit
from app.services.weekly_pulse_cycle_service import upsert_leader_membership
from app.utils.constants import PRIVILEGED_ROLES, TaskStatus

TERMINAL = {TaskStatus.COMPLETED, TaskStatus.CANCELLED}


def manager(user, settings):
    return bool(user and not user.is_archived and not user.is_blocked and
                (user.telegram_id in settings.admin_ids or user.role in PRIVILEGED_ROLES))


def can_manage(task, user, settings):
    return bool(user and (task.creator_id == user.id or manager(user, settings)))


def meta(task):
    return (task.reward_json or {}).get('leaders', {})


def set_meta(task, **values):
    task.reward_json = {**(task.reward_json or {}), 'leaders': {**meta(task), **values}}


async def roster(session, chat_id):
    return list((await session.scalars(select(User).join(LeaderChatMembership,
        LeaderChatMembership.user_id == User.id).where(
        LeaderChatMembership.leader_chat_id == chat_id,
        LeaderChatMembership.is_weekly_pulse_eligible.is_(True),
        User.is_archived.is_(False), User.is_blocked.is_(False)).order_by(User.first_name, User.id))).all())


async def verify_member(session, bot, settings, user):
    if not user or user.is_archived or user.is_blocked or not settings.leaders_chat_id:
        return False
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
        q = q.with_for_update(of=Task)
    return await session.scalar(q)


async def create_task(session, settings, creator, *, title, description='', assignee_id=None,
                      deadline=None, priority='normal', project_id=None, source='telegram', request_key=None):
    if not manager(creator, settings):
        raise ValueError('Создавать задачи могут только руководители.')
    if not settings.leaders_chat_id or settings.leaders_chat_id == settings.general_chat_id:
        raise ValueError('Рабочий чат ЛИДЕРЫ не привязан.')
    if not title.strip():
        raise ValueError('Укажите задачу.')
    if assignee_id is not None and assignee_id not in {u.id for u in await roster(session, settings.leaders_chat_id)}:
        raise ValueError('Исполнитель должен состоять в ЛИДЕРАХ и подключить бота.')
    if deadline:
        if deadline.tzinfo is None:
            raise ValueError('Для срока требуется часовой пояс.')
        if deadline <= datetime.now(timezone.utc):
            raise ValueError('Срок должен быть в будущем.')
    task = Task(title=title.strip()[:255], description=description.strip()[:5000] or title.strip(),
        assignee_id=assignee_id, creator_id=creator.id, deadline=deadline, points=10,
        task_type='private', project_id=project_id,
        remind_at=deadline-timedelta(hours=24) if deadline else None)
    set_meta(task, priority=priority, created_via=source, request_key=request_key)
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
    result = await session.execute(update(Task).where(Task.id == task.id,
        Task.assignee_id.is_(None), Task.status.in_([TaskStatus.NEW, TaskStatus.PUBLISHED]))
        .values(assignee_id=user.id).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise ValueError('Задачу уже взял другой участник.')
    await session.refresh(task)
    await audit(session, actor_id=user.id, action='leaders.task_claimed', entity_type='task', entity_id=task.id)


async def change_task(session, settings, task, user, action, value=None):
    if task.status in TERMINAL:
        raise ValueError('Задача уже закрыта.')
    if action in {'start','block','submit','question'}:
        if task.assignee_id != user.id:
            raise ValueError('Действие доступно исполнителю.')
    elif not can_manage(task, user, settings):
        raise ValueError('Действие доступно автору и руководству.')
    old = {'status':str(task.status), 'assignee_id':task.assignee_id,
           'deadline':(task.deadline.isoformat() if task.deadline else "") if task.deadline else None}
    if action == 'start':
        if task.status not in {TaskStatus.NEW, TaskStatus.PUBLISHED, TaskStatus.OVERDUE}:
            raise ValueError('Задача уже начата.')
        task.status = TaskStatus.IN_PROGRESS
    elif action == 'assign':
        if value is not None and value not in {u.id for u in await roster(session, settings.leaders_chat_id)}:
            raise ValueError('Исполнитель не состоит в ЛИДЕРАХ.')
        if task.status == TaskStatus.REVIEW:
            raise ValueError('Сначала примите или верните текущий результат.')
        task.assignee_id = value
    elif action == 'deadline':
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
                entity_id=task.id, old_value=old, new_value={'status':str(task.status)})


def deadline_label(value, fmt='%d.%m.%Y %H:%M'):
    from zoneinfo import ZoneInfo
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(ZoneInfo('Asia/Yerevan')).strftime(fmt) if value else 'Без срока'
