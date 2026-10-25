"""Private conversation views shared by existing participant/admin handlers."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from app.database.models import SupportMessage, User, UserQuestion
from app.services.support_service import CATEGORIES, support_thread
from app.services.feature_flags import Feature, feature_enabled
from datetime import timezone
from zoneinfo import ZoneInfo

STATUS_LABELS = {'thread_waiting': '🟡 Ожидает ответа', 'thread_answered': '🟢 Ответ подготовлен',
                 'thread_closed': '✅ Закрыто', 'new': '🟡 Ожидает ответа', 'open': '🟡 В работе',
                 'answered': '🟢 Ответ доставлен', 'answer_pending': '⏳ Ответ в очереди',
                 'answer_failed': '⚠️ Ответ не доставлен', 'answer_review': '⚠️ Доставка требует проверки'}


def button(text, callback):
    return InlineKeyboardButton(text=text, callback_data=callback)


async def show_my_support(message, session, user, *, page=0):
    conditions = UserQuestion.user_id == user.id
    count = int(await session.scalar(select(func.count()).select_from(UserQuestion).where(conditions)) or 0)
    page = min(max(0, page), max(0, (count-1)//8))
    items = list((await session.scalars(select(UserQuestion).where(conditions)
        .order_by(UserQuestion.id.desc()).offset(page*8).limit(8))).all())
    rows = [[button(f'#{item.id} · {STATUS_LABELS.get(item.status, "Обращение")}',
                    f'support:mine:item:{item.id}')] for item in items]
    nav = []
    if page:
        nav.append(button('←', f'support:mine:page:{page-1}'))
    if (page+1)*8 < count:
        nav.append(button('→', f'support:mine:page:{page+1}'))
    if nav:
        rows.append(nav)
    rows.extend([[button('✍️ Новый вопрос', 'question:start')], [button('← Связь', 'contact:menu')]])
    await message.answer(f'💬 Мои обращения · {count}\n\n'
        'История доступна вам и уполномоченным администраторам. Обращения не анонимные.\n'
        'Выберите обращение, чтобы прочитать ответ или дополнить вопрос.',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def show_support_thread(message, session, settings, *, question_id, actor_id, staff=False, page=None):
    item = await support_thread(session, question_id, actor_id, settings, staff=staff)
    owner = await session.get(User, item.user_id)
    assignee = await session.get(User, item.assigned_to) if item.assigned_to else None
    count = int(await session.scalar(select(func.count()).select_from(SupportMessage).where(
        SupportMessage.question_id == item.id)) or 0)
    last_page = max(0, (count-1)//3)
    page = last_page if page is None else min(max(0, page), last_page)
    entries = list((await session.scalars(select(SupportMessage).where(SupportMessage.question_id == item.id)
        .order_by(SupportMessage.id).offset(page*3).limit(3))).all())
    body = (f'💬 ЭРА · Обращение #{item.id}\n{STATUS_LABELS.get(item.status, "Обращение")}\n'
        f'Тема: {CATEGORIES.get(item.category, "Общий вопрос")}\n'
        f'Ответственный: {assignee.first_name if assignee else "ещё не назначен"}\n')
    if staff:
        body += f'Участник: {owner.first_name if owner else "Профиль недоступен"}\n'
    if count > 3:
        body += f'История: {page+1} из {last_page+1}\n'
    body += '\n'
    if not entries:
        body += item.text
        if item.admin_answer:
            body += f'\n\nАдминистратор:\n{item.admin_answer}'
        if item.status == 'answer_review':
            body += '\n\n⚠️ Старая доставка требует сверки. Проверьте переписку перед новым ответом. Старое сообщение повторно не отправляется.'
        elif item.status == 'answer_failed':
            body += '\n\n⚠️ Старый ответ не доставлен. Он сохранён в истории; новый ответ оформляется отдельно.'
    else:
        for entry in entries:
            label = 'Администратор' if entry.direction == 'staff' else 'Участник'
            status = {'pending': ' · в очереди', 'failed': ' · доставка не удалась',
                      'uncertain': ' · доставка требует проверки', 'unreachable': ' · получатель недоступен'}.get(entry.delivery_status, '')
            stamp = entry.created_at
            stamp = (stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp).astimezone(ZoneInfo('Europe/Moscow'))
            body += f'{label} · {stamp:%d.%m %H:%M} МСК{status}\n{entry.text}\n\n'
    prefix = 'admin:support:thread' if staff else 'support:mine'
    editable = bool(owner and feature_enabled(settings, Feature.SUPPORT_THREADS, owner.telegram_id))
    rows = []
    nav = []
    if page:
        nav.append(button('← Раньше', f'{prefix}:history:{item.id}:{page-1}'))
    if page < last_page:
        nav.append(button('Дальше →', f'{prefix}:history:{item.id}:{page+1}'))
    if nav:
        rows.append(nav)
    if editable and item.status != 'thread_closed' and item.status != 'answer_pending':
        rows.append([button('✍️ Ответить' if staff else '✍️ Дополнить вопрос',
            f'{prefix}:reply:{item.id}:{item.thread_revision}')])
    if staff and editable:
        rev = item.thread_revision
        if item.assigned_to is None:
            rows.append([button('🙋 Взять в работу', f'{prefix}:claim:{item.id}:{rev}')])
        elif item.assigned_to == actor_id:
            rows.append([button('Передать в общую очередь', f'{prefix}:release:{item.id}:{rev}')])
        if item.status != 'thread_closed':
            rows.append([button('👤 Назначить ответственного', f'{prefix}:assignees:{item.id}:{rev}:0')])
        action = 'reopen' if item.status == 'thread_closed' else 'close'
        rows.append([button('↩️ Открыть снова' if action == 'reopen' else '✅ Закрыть', f'{prefix}:{action}:{item.id}:{rev}')])
        rows.append([button('🏷 Изменить тему', f'{prefix}:categories:{item.id}:{rev}')])
    if item.file_id and not entries:
        rows.append([button('📎 Вложение', f'{prefix}:file:{item.id}:{item.thread_revision}')])
    for entry in entries:
        if entry.file_id:
            label = 'администратора' if entry.direction == 'staff' else 'участника'
            stamp = entry.created_at.strftime('%d.%m')
            rows.append([button(f'📎 Файл {label} · {stamp}', f'{prefix}:attachment:{item.id}:{entry.id}')])
    rows.append([button('← Обращения', 'admin:questions' if staff else 'support:mine:page:0')])
    # Keep each Telegram message below its limit, with buttons only on the last.
    parts = [body[i:i+3000] for i in range(0, len(body), 3000)]
    for index, part in enumerate(parts):
        await message.answer(part, parse_mode=None,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if index == len(parts)-1 else None)
