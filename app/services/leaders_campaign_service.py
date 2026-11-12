"""Create Leaders campaigns in the existing Broadcast queue and delivery ledger."""
import hashlib

from sqlalchemy import select, text as sql_text

from app.database.models import Broadcast
from app.database.system_models import NotificationDelivery
from app.services import leaders_access_service as access
from app.services import leaders_workspace as workspace
from app.services.admin_broadcast_service import _deliver_campaign, control_broadcast
from app.utils.constants import ApplicationStatus


async def delivery_options(session, settings, *, scoped=False):
    """Offer only available destinations; personal delivery stays an explicit choice."""
    if scoped:
        return [('Лично', 'dm')], None
    try:
        from app.services.leaders_topics_service import delivery_topic
        await delivery_topic(session, settings.leaders_chat_id, 'important')
    except ValueError:
        return [('Лично', 'dm')], (
            'Отправка в чат пока недоступна: панель «Важно» не подтверждена. '
            'Черновик сохранён. Можно выбрать личную доставку или отменить. '
            'Для восстановления ответьте /leaders_repair important на существующую панель бота в теме «Важно».'
        )
    return [('В чат', 'group'), ('Лично', 'dm'), ('В чат и лично', 'both')], None


async def recipients(session, settings, actor, department_id=None, direction_id=None):
    if not await access.permitted_scope(session, actor, settings, department_id=department_id,
                                       direction_id=direction_id, permission='broadcasts.create'):
        raise PermissionError('Нет права рассылать сообщения этой команде.')
    return [u for u in await workspace.roster(session, settings.leaders_chat_id)
            if access.in_scope(u, department_id, direction_id) and u.application_status == ApplicationStatus.APPROVED]


async def create(session, settings, actor, *, body, request_key, mode='group',
                 department_id=None, direction_id=None, acknowledge=False):
    if not body.strip() or len(body) > 2800 or mode not in {'group', 'dm', 'both'}:
        raise ValueError('Проверьте текст и способ доставки.')
    if not settings.leaders_chat_id or settings.leaders_chat_id == settings.general_chat_id:
        raise ValueError('Рабочий чат лидеров не привязан.')
    users = await recipients(session, settings, actor, department_id, direction_id)
    if (department_id or direction_id) and mode != 'dm':
        raise ValueError('Сообщение направлению отправляется лично, без публикации всей команде.')
    if mode in {'group', 'both'}:
        from app.services.leaders_topics_service import delivery_topic
        await delivery_topic(session, settings.leaders_chat_id, 'important')
    key = hashlib.sha256(f'leaders:{actor.id}:{request_key}'.encode()).hexdigest()
    if session.bind.dialect.name == 'postgresql':
        await session.execute(sql_text('SELECT pg_advisory_xact_lock(:key)'),
                              {'key': int.from_bytes(bytes.fromhex(key)[:8], 'big', signed=True)})
    item = await session.scalar(select(Broadcast).where(Broadcast.audience_filter_json['campaign_key'].as_string() == key))
    if item:
        data = item.audience_filter_json
        if (item.text, data.get('mode'), data.get('department_id'), data.get('direction_id'), data.get('acknowledge')) != (
                body.strip(), mode, department_id, direction_id, acknowledge):
            raise ValueError('Подтверждение уже использовано для другой рассылки.')
        return item
    item = Broadcast(title=body[:100], text=body.strip(), author_id=actor.id, audience_type='leaders', status='sending',
        audience_filter_json={'campaign_key':key, 'recipient_ids':[u.id for u in users], 'recipients':[u.id for u in users],
            'chat_id':settings.leaders_chat_id, 'mode':mode, 'acknowledge':acknowledge,
            'department_id':department_id, 'direction_id':direction_id, 'kind':'important' if acknowledge else 'normal'})
    session.add(item)
    await session.flush()
    return item


async def send(session, settings, bot, item):
    return await _deliver_campaign(bot, settings, session, item)


async def control(session, settings, actor, item_id, action):
    item = await session.get(Broadcast, item_id)
    if not item or item.audience_type != 'leaders':
        raise ValueError('Рассылка не найдена.')
    data = item.audience_filter_json
    await recipients(session, settings, actor, data.get('department_id'), data.get('direction_id'))
    if item.author_id != actor.id and not await access.executive(session,actor,settings):
        raise PermissionError('Управлять можно только своей рассылкой.')
    return await control_broadcast(session, settings, actor=actor, campaign_id=item.id, action=action, workcenter=True)


async def summary(session, item):
    from sqlalchemy import func
    from app.database.leadership_models import BroadcastAcknowledgement
    counts = dict((await session.execute(select(NotificationDelivery.status,func.count()).where(
        NotificationDelivery.delivery_key.like(f'admin-campaign:{item.id}:%')).group_by(NotificationDelivery.status))).all())
    data = item.audience_filter_json or {}
    return {'id':item.id,'text':item.text,'status':item.status,'kind':data.get('kind','normal'),
            'mode':data.get('mode','group'), 'recipients':len(data.get('recipients',[])),
            'sent':counts.get('sent',0),'uncertain':counts.get('uncertain',0),
            'unreachable':counts.get('blocked',0)+counts.get('unreachable',0),
            'read':int(await session.scalar(select(func.count()).select_from(BroadcastAcknowledgement)
                .where(BroadcastAcknowledgement.broadcast_id==item.id)) or 0)}
