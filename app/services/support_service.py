"""Existing UserQuestion intake: canonical permission check and durable notices."""
import json
import hashlib

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database.models import AppSetting, User, UserQuestion
from app.services.audit_service import audit
from app.services.notification_service import admin_notification_recipients, safe_send_once
from app.utils.constants import ApplicationStatus


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
