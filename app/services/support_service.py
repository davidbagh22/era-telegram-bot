"""Existing UserQuestion intake: canonical permission check and durable notices."""
import json
import hashlib
from datetime import datetime, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database.models import AppSetting, SupportMessage, User, UserQuestion
from app.services.staff_access_service import can_operate_queue
from app.services.feature_flags import Feature, feature_enabled
from app.services.audit_service import audit
from app.services.notification_service import admin_notification_recipients, safe_send_once
from app.utils.constants import ApplicationStatus

CATEGORIES = {'general': 'Общий вопрос', 'events': 'Мероприятия', 'projects': 'Проекты и задачи',
              'points': 'Баллы и достижения', 'access': 'Доступ и профиль'}
THREAD_STATUSES = {'thread_waiting', 'thread_answered', 'thread_closed'}


async def support_actor(session, user_id, settings, *, staff=False):
    actor = await session.scalar(select(User).where(User.id == user_id).execution_options(populate_existing=True))
    if (actor is None or actor.is_blocked or actor.is_archived
            or actor.application_status != ApplicationStatus.APPROVED
            or not feature_enabled(settings, Feature.SUPPORT_THREADS, actor.telegram_id)
            or staff and not await can_operate_queue(session, actor, settings, "support.manage")):
        raise PermissionError('support_access_denied')
    return actor


async def support_thread(session, question_id, actor_id, settings, *, staff=False, lock=False):
    actor = await support_actor(session, actor_id, settings, staff=staff)
    query = select(UserQuestion).where(UserQuestion.id == question_id).execution_options(populate_existing=True)
    item = await session.scalar(query.with_for_update() if lock else query)
    if item is None or not staff and item.user_id != actor.id:
        raise PermissionError('support_access_denied')
    if staff and lock:
        owner = await session.get(User, item.user_id)
        if owner is None or not feature_enabled(settings, Feature.SUPPORT_THREADS, owner.telegram_id):
            raise PermissionError('support_owner_outside_rollout')
    return item


async def _convert_thread(session, item):
    if item.status in THREAD_STATUSES:
        return
    # A legacy answer may currently be in Telegram flight. Let its existing
    # worker finish; never send it again with a new operation key.
    if item.status == 'answer_pending':
        raise ValueError('legacy_delivery_pending')
    failed = item.status == 'answer_failed'
    uncertain = item.status == 'answer_review'
    session.add(SupportMessage(question_id=item.id, author_id=item.user_id, direction='participant',
        source_key=f'legacy-question:{item.id}', text=item.text, file_id=item.file_id,
        delivery_status='legacy', created_at=item.created_at))
    if item.admin_answer:
        session.add(SupportMessage(question_id=item.id, author_id=item.answered_by, direction='staff',
            source_key=f'legacy-answer:{item.id}', text=item.admin_answer,
            delivery_status='failed' if failed else 'uncertain' if uncertain else 'legacy',
            created_at=item.updated_at))
    item.thread_revision = 1
    item.category = item.category or 'general'
    answered = bool(item.admin_answer and not failed and not uncertain)
    item.status = 'thread_answered' if answered else 'thread_waiting'
    item.waiting_since = None if answered else item.created_at
    await session.flush()


def support_message_input(message):
    """Read one Telegram text/photo/document without downloading private files."""
    photo, document = getattr(message, 'photo', None), getattr(message, 'document', None)
    file_id = photo[-1].file_id if photo else document.file_id if document else None
    text = (message.text or getattr(message, 'caption', None) or '').strip()
    if text.startswith('/') or len(text) > 1500 or not (text or file_id):
        raise ValueError('invalid_message')
    return text or '📎 Вложение', file_id


async def support_attachment(session, settings, *, question_id, message_id, actor_id, staff=False):
    await support_thread(session, question_id, actor_id, settings, staff=staff)
    entry = await session.scalar(select(SupportMessage).where(
        SupportMessage.id == message_id, SupportMessage.question_id == question_id))
    if entry is None or not entry.file_id:
        raise PermissionError('support_attachment_unavailable')
    return entry.file_id


async def support_assignees(session, settings):
    """Only active approved admins inside this feature's explicit audience."""
    candidates = (await session.scalars(select(User).where(
        User.application_status == ApplicationStatus.APPROVED,
        User.is_blocked.is_(False), User.is_archived.is_(False),
    ).order_by(User.first_name, User.id))).all()
    return [actor for actor in candidates
            if feature_enabled(settings, Feature.SUPPORT_THREADS, actor.telegram_id)
            and await can_operate_queue(session, actor, settings, "support.manage")]


async def append_support_message(session, settings, *, question_id, actor_id, staff, text, source_key, expected_revision, file_id=None):
    """One row lock protects the conversation and stale admin reply snapshots."""
    text = text.strip()
    if (not text or len(text) > 1500 or not source_key or len(source_key) > 120
            or file_id is not None and (not isinstance(file_id, str) or not file_id or len(file_id) > 255)):
        raise ValueError('invalid_message')
    item = await support_thread(session, question_id, actor_id, settings, staff=staff, lock=True)
    key = 'support-message:' + hashlib.sha256(f'{actor_id}:{source_key}'.encode()).hexdigest()
    existing = await session.scalar(select(SupportMessage).where(SupportMessage.source_key == key))
    if existing:
        if (existing.question_id != item.id or existing.text != text or existing.file_id != file_id
                or existing.direction != ('staff' if staff else 'participant')):
            raise ValueError('message_source_conflict')
        return existing, False
    if item.thread_revision != expected_revision:
        raise ValueError('stale_thread')
    await _convert_thread(session, item)
    if item.status == 'thread_closed':
        raise ValueError('closed_thread')
    message = SupportMessage(question_id=item.id, author_id=actor_id,
        direction='staff' if staff else 'participant', source_key=key, text=text, file_id=file_id)
    session.add(message)
    now = datetime.now(timezone.utc)
    if staff:
        item.status, item.waiting_since = 'thread_answered', None
    else:
        # Several participant messages before a response do not reset the SLA.
        item.waiting_since = item.waiting_since or now
        item.status = 'thread_waiting'
    item.thread_revision += 1
    await session.flush()
    await audit(session, actor_id=actor_id, action='support.message', entity_type='question',
        entity_id=item.id, new_value={'message_id': message.id, 'direction': message.direction})
    return message, True


async def update_support_thread(session, settings, *, question_id, actor_id, expected_revision, action, category=None, assignee_id=None):
    item = await support_thread(session, question_id, actor_id, settings, staff=True, lock=True)
    if item.thread_revision != expected_revision:
        raise ValueError('stale_thread')
    if action not in {'claim', 'release', 'assign', 'close', 'reopen', 'category'} or action == 'category' and category not in CATEGORIES:
        raise ValueError('invalid_action')
    if action == 'assign':
        # Recheck the target at submission time, including revoked access and
        # rollout changes since the selector was opened.
        target = await support_actor(session, assignee_id, settings, staff=True)
        if item.status == 'thread_closed':
            raise ValueError('closed_thread')
    await _convert_thread(session, item)
    if action == 'claim':
        if item.assigned_to not in {None, actor_id}:
            raise ValueError('already_assigned')
        item.assigned_to = actor_id
    elif action == 'release':
        if item.assigned_to != actor_id:
            raise PermissionError('not_assignee')
        item.assigned_to = None
    elif action == 'assign':
        item.assigned_to = target.id
    elif action == 'close':
        item.status, item.waiting_since = 'thread_closed', None
    elif action == 'reopen':
        if item.status != 'thread_closed':
            raise ValueError('not_closed')
        item.status, item.waiting_since = 'thread_waiting', datetime.now(timezone.utc)
    else:
        item.category = category
    item.thread_revision += 1
    if action == 'assign':
        session.add(AppSetting(key=f'support-assignment:{item.id}:{item.thread_revision}',
            value={'question_id': item.id, 'assignee_id': target.id}))
    await audit(session, actor_id=actor_id, action=f'support.{action}', entity_type='question',
        entity_id=item.id, new_value={'revision': item.thread_revision, 'status': item.status,
            'category': item.category, 'assigned_to': item.assigned_to})
    await session.flush()
    return item


async def deliver_support_thread_messages(bot, settings, session_factory):
    """Drain committed messages even when rollout is subsequently disabled.

    Existing safe_send_once owns RetryAfter, retries and uncertain outcomes.
    Never change an old support-answer key or resend a migrated legacy message.
    """
    await _deliver_support_assignments(bot, settings, session_factory)
    async with session_factory() as session:
        ids = list((await session.scalars(select(SupportMessage.id).where(
            SupportMessage.delivery_status == 'pending').order_by(SupportMessage.id).limit(30))).all())
    for message_id in ids:
        async with session_factory() as session:
            message = await session.scalar(select(SupportMessage).where(SupportMessage.id == message_id)
                .with_for_update().execution_options(populate_existing=True))
            if not message or message.delivery_status != 'pending':
                continue
            item = await session.get(UserQuestion, message.question_id)
            owner = await session.get(User, item.user_id)
            if owner is None or owner.is_blocked or owner.is_archived:
                message.delivery_status = 'unreachable'
                await session.commit()
                continue
            if message.direction == 'staff':
                recipients = {owner.telegram_id}
                body = f'💬 ЭРА · Ответ на обращение #{item.id}\n\n{message.text}'
                if message.file_id:
                    body += '\n\n📎 Файл сохранён в переписке. Нажмите «Открыть переписку».'
                callback = f'support:mine:item:{item.id}'
            else:
                assignee = await session.get(User, item.assigned_to) if item.assigned_to else None
                if (assignee and not assignee.is_blocked and not assignee.is_archived
                        and assignee.application_status == ApplicationStatus.APPROVED
                        and await can_operate_queue(session, assignee, settings, "support.manage")):
                    recipients = {assignee.telegram_id}
                else:
                    recipients = {int(i) for i in await admin_notification_recipients(settings) if int(i) > 0}
                body = f'💬 ЭРА · Дополнение к обращению #{item.id}\n\nУчастник добавил сообщение. Откройте личную карточку обращения.'
                callback = f'admin:support:item:{item.id}'
            if not recipients:
                continue
            statuses = []
            for recipient in sorted(recipients):
                receipt = await safe_send_once(bot, settings, recipient, body,
                    delivery_key=f'support-thread:{message.id}:{hashlib.sha256(str(recipient).encode()).hexdigest()[:12]}',
                    notification_type='support_thread', parse_mode=None,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                        text='Открыть переписку', callback_data=callback)]]))
                statuses.append(receipt.status if receipt.status != 'failed' or receipt.attempt_count >= 3 else 'pending')
            if 'pending' not in statuses and 'sending' not in statuses:
                message.delivery_status = ('sent' if all(s == 'sent' for s in statuses)
                    else 'uncertain' if any(s in {'uncertain', 'conflict', 'sent_unconfirmed'} for s in statuses) else 'failed')
            await session.commit()


async def _deliver_support_assignments(bot, settings, session_factory):
    async with session_factory() as session:
        keys = list((await session.scalars(select(AppSetting.key).where(
            AppSetting.key.like('support-assignment:%')).order_by(AppSetting.key).limit(20))).all())
    for key in keys:
        async with session_factory() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update()
                .execution_options(populate_existing=True))
            if row is None:
                continue
            data = json.loads(row.value) if isinstance(row.value, str) else row.value
            item = await session.get(UserQuestion, data['question_id'])
            target = await session.get(User, data['assignee_id'])
            if (not item or item.status == 'thread_closed' or item.assigned_to != data['assignee_id']
                    or not target or target.is_blocked or target.is_archived
                    or target.application_status != ApplicationStatus.APPROVED
                    or not await can_operate_queue(session, target, settings, "support.manage")):
                await session.delete(row)
                await session.commit()
                continue
            receipt = await safe_send_once(bot, settings, target.telegram_id,
                f'👤 ЭРА · Обращение #{item.id}\n\nВы назначены ответственным. Текст и файлы доступны в личной карточке.',
                delivery_key=key, notification_type='support_assignment', parse_mode=None,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                    text='Открыть обращение', callback_data=f'admin:support:item:{item.id}')]]))
            if (receipt.status in {'sent', 'blocked', 'unreachable', 'uncertain', 'conflict', 'skipped', 'sent_unconfirmed'}
                    or receipt.status == 'failed' and receipt.attempt_count >= 3):
                await session.delete(row)
            await session.commit()


async def create_support_question(session, *, user_id, source_key, text, file_id=None, context=None):
    if not source_key or len(source_key) > 120 or not text.strip():
        raise ValueError('invalid_question')
    actor = await session.scalar(select(User).where(User.id == user_id).with_for_update()
                                 .execution_options(populate_existing=True))
    if (actor is None or actor.application_status != ApplicationStatus.APPROVED
            or actor.is_blocked or actor.is_archived):
        raise PermissionError('approved_participant_required')
    digest = hashlib.sha256(source_key.encode()).hexdigest()[:32]
    key = f'support-intake-source:{user_id}:{digest}'
    if session.bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    await session.execute(insert(AppSetting).values(key=key, value={})
                          .on_conflict_do_nothing(index_elements=['key']))
    marker = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update()
                                  .execution_options(populate_existing=True))
    value = json.loads(marker.value) if isinstance(marker.value, str) else marker.value
    if value.get('question_id'):
        question = await session.get(UserQuestion, value['question_id'])
        if question is None or question.user_id != user_id or question.text != text or question.file_id != file_id:
            raise ValueError('question_source_conflict')
        return question, False
    question = UserQuestion(user_id=user_id, text=text, file_id=file_id)
    session.add(question)
    await session.flush()
    marker.value = {'question_id': question.id}
    session.add(AppSetting(key=f'support-intake-notice:{question.id}', value={'question_id': question.id}))
    await audit(session, actor_id=user_id, action='question.created', entity_type='user_question',
                entity_id=question.id, new_value={'source': 'faq' if context else 'bot', **(context or {})})
    await session.flush()
    return question, True


async def deliver_support_intake_notices(bot, settings, session_factory):
    async with session_factory() as session:
        keys = list((await session.scalars(select(AppSetting.key).where(
            AppSetting.key.like('support-intake-notice:%')).order_by(AppSetting.key).limit(10))).all())
    if not keys:
        return
    recipients = {int(i) for i in await admin_notification_recipients(settings) if int(i) > 0}
    if not recipients:
        return
    for key in keys:
        async with session_factory() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update()
                                       .execution_options(populate_existing=True))
            if row is None:
                continue
            value = json.loads(row.value) if isinstance(row.value, str) else row.value
            question = await session.get(UserQuestion, value['question_id'])
            author = await session.get(User, question.user_id) if question else None
            if question is None or author is None or author.is_archived:
                await session.delete(row)
                await session.commit()
                continue
            body = (f'💬 ЭРА · Новое обращение #{question.id}\n\n'
                    f'{question.text[:1200]}\n\nПолный текст и вложение — в карточке обращения.')
            markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text='Открыть обращение в боте', callback_data=f'admin:support:item:{question.id}')]])
            complete = True
            for recipient in sorted(recipients):
                delivery = await safe_send_once(bot, settings, recipient, body,
                    delivery_key=f'support-intake:{question.id}:admin:{hashlib.sha256(str(recipient).encode()).hexdigest()[:12]}',
                    notification_type='support_intake', parse_mode=None, reply_markup=markup)
                complete &= (delivery.status in {'sent', 'blocked', 'unreachable', 'uncertain', 'conflict', 'skipped'}
                             or delivery.status == 'failed' and delivery.attempt_count >= 3)
            if complete:
                await session.delete(row)
            await session.commit()
