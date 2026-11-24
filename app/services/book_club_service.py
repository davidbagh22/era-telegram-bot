"""Existing opt-in club: durable progress, explicit consent, Yerevan schedule."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.content.literature_issues import LAW_TITLES as LAW_TITLES, get_issue, render_issue
from app.database.models import AppSetting, User
from app.services.notification_service import safe_send_once
from app.services.general_topics_service import send_general_topic
from app.services.points_service import add_points, make_idempotency_key
from app.utils.constants import ApplicationStatus

PROGRAM_START = date(2026, 10, 10)
SPECIAL_OPENING_DATE = date(2026, 10, 10)

# Opting in to a reading club does not authorize the organization to publish
# every future issue. Exact day + chat + rendered text must be approved.
# Code frozenset stays empty (tests may patch it). Production approvals live in
# AppSetting so editors can approve without a redeploy. Manual reading still works.
APPROVED_SCHEDULED_LITERATURE_ISSUES: frozenset[tuple[str, str, str]] = frozenset()
SERIES_APPROVAL_KEY_PREFIX = 'literature-series-approval:'


def scheduled_literature_issue_approval_key(
    on_date: date, chat_id: int | str, number: int
) -> tuple[str, str, str]:
    payload = {
        'topic': 'literature',
        'parse_mode': 'HTML',
        'text': render_issue(number),
    }
    digest = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')).hexdigest()
    return (on_date.isoformat(), str(chat_id), digest)


def series_approval_setting_key(on_date: date, chat_id: int | str) -> str:
    return f'{SERIES_APPROVAL_KEY_PREFIX}{on_date.isoformat()}:{chat_id}'


def publication_number(on_date: date, start_date: date = PROGRAM_START) -> int | None:
    """One issue every calendar day for 48 days from the program start."""
    number = (on_date - start_date).days + 1
    return number if 1 <= number <= 48 else None


def yerevan_today() -> date:
    return datetime.now(ZoneInfo('Asia/Yerevan')).date()


def last_readable_issue_number(on_date: date | None = None, start_date: date = PROGRAM_START) -> int:
    """Latest issue participants may open in the catalog (never beyond 48)."""
    day = on_date or yerevan_today()
    number = (day - start_date).days + 1
    if number < 1:
        return 1
    return min(number, 48)


async def series_issue_is_approved(
    session: AsyncSession, on_date: date, chat_id: int | str, number: int
) -> bool:
    key = scheduled_literature_issue_approval_key(on_date, chat_id, number)
    if key in APPROVED_SCHEDULED_LITERATURE_ISSUES:
        return True
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == series_approval_setting_key(on_date, chat_id))
    )
    if not row or not isinstance(row.value, dict):
        return False
    if row.value.get('revoked'):
        return False
    return (
        int(row.value.get('number') or 0) == number
        and row.value.get('digest') == key[2]
    )


async def approve_series_issue(
    session: AsyncSession,
    *,
    on_date: date,
    chat_id: int | str,
    number: int,
    actor_id: int,
) -> dict:
    get_issue(number)
    if publication_number(on_date) != number:
        raise ValueError('issue_date_mismatch')
    day_key, chat_key, digest = scheduled_literature_issue_approval_key(on_date, chat_id, number)
    setting_key = series_approval_setting_key(on_date, chat_id)
    await _insert_setting(session, key=setting_key, value={}, actor_id=actor_id)
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == setting_key).with_for_update()
        .execution_options(populate_existing=True)
    )
    value = {
        'date': day_key,
        'chat_id': chat_key,
        'number': number,
        'digest': digest,
        'revoked': False,
        'approved_at': datetime.now(ZoneInfo('Asia/Yerevan')).isoformat(),
        'approved_by': actor_id,
    }
    row.value, row.updated_by = value, actor_id
    from app.services.audit_service import audit
    await audit(
        session, actor_id=actor_id, action='literature.series_approved',
        entity_type='content', entity_id=number, new_value=value,
    )
    return value


async def revoke_series_issue(
    session: AsyncSession,
    *,
    on_date: date,
    chat_id: int | str,
    actor_id: int,
) -> dict | None:
    setting_key = series_approval_setting_key(on_date, chat_id)
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == setting_key).with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row or not isinstance(row.value, dict):
        return None
    value = {**row.value, 'revoked': True, 'revoked_at': datetime.now(ZoneInfo('Asia/Yerevan')).isoformat(),
             'revoked_by': actor_id}
    row.value, row.updated_by = value, actor_id
    from app.services.audit_service import audit
    await audit(
        session, actor_id=actor_id, action='literature.series_revoked',
        entity_type='content', entity_id=int(value.get('number') or 0), new_value=value,
    )
    return value


async def series_issue_delivery(
    session: AsyncSession, start_day: date, number: int
):
    from app.database.system_models import NotificationDelivery
    return await session.scalar(select(NotificationDelivery).where(
        NotificationDelivery.delivery_key == f'general-topic:literature:issue:{start_day.isoformat()}:{number}'
    ))


async def series_status(
    session: AsyncSession, settings: Settings, *, on_date: date | None = None
) -> dict:
    """Editor-facing status for the daily 48-issue series (Yerevan calendar)."""
    day = on_date or yerevan_today()
    chat_id = settings.general_chat_id
    number = publication_number(day)
    start_row = await session.scalar(select(AppSetting).where(AppSetting.key == 'book_club_start_date'))
    start_day = date.fromisoformat(start_row.value['date']) if start_row else PROGRAM_START
    if number is None:
        if day < start_day:
            return {
                'label': 'Ждёт старта',
                'reason': f'Серия начинается {start_day.isoformat()}',
                'number': None, 'date': day.isoformat(), 'chat_id': chat_id,
                'approved': False, 'published': False, 'action': 'none',
                'preview': '',
            }
        return {
            'label': 'Серия завершена',
            'reason': 'Все 48 выпусков по календарю уже прошли. Накопленные выпуски автоматически не рассылаются.',
            'number': 48, 'date': day.isoformat(), 'chat_id': chat_id,
            'approved': False, 'published': False, 'action': 'none',
            'preview': render_issue(48)[:500],
        }
    if not chat_id:
        return {
            'label': 'Нужна проверка',
            'reason': 'Не настроен general_chat_id — публиковать некуда.',
            'number': number, 'date': day.isoformat(), 'chat_id': chat_id,
            'approved': False, 'published': False, 'action': 'none',
            'preview': render_issue(number)[:900],
        }
    approved = await series_issue_is_approved(session, day, chat_id, number)
    receipt = await series_issue_delivery(session, start_day, number)
    published = bool(receipt and receipt.status in {'sent', 'already_sent'})
    uncertain = bool(receipt and receipt.status in {'uncertain', 'conflict'})
    # daily_job prefers the editorial queue: when enabled (even paused/empty),
    # run_editorial_queue returns True and the 48-issue series is skipped.
    editorial = await editorial_settings(session)
    editorial_blocks_series = bool(editorial.get('enabled'))
    if published:
        label, reason, action = 'Опубликован', f'Доставка в чат: {receipt.status}', 'none'
    elif uncertain:
        label, reason, action = (
            'Нужна проверка',
            f'Исход отправки неизвестен ({receipt.status}). Повтор остановлен до сверки.',
            'none',
        )
    elif approved and editorial_blocks_series:
        paused = ' (на паузе)' if editorial.get('paused') else ''
        label, reason, action = (
            'Нужна проверка',
            (
                f'Выпуск одобрен, но включена редакционная очередь{paused}. '
                'Пока она активна, серия в 19:00 не уходит — отключите очередь, '
                'чтобы возобновить плановую доставку.'
            ),
            'revoke',
        )
    elif approved:
        label, reason, action = (
            'Запланирован',
            'Одобрен. Уйдёт один раз в 19:00 Asia/Yerevan (без догона прошлых дней).',
            'revoke',
        )
    else:
        label, reason, action = (
            'Ждёт согласования',
            'Плановая отправка блокируется, пока редактор не одобрит точный текст и дату.',
            'approve',
        )
    return {
        'label': label,
        'reason': reason,
        'number': number,
        'date': day.isoformat(),
        'chat_id': chat_id,
        'approved': approved,
        'published': published,
        'action': action,
        'editorial_blocks_series': editorial_blocks_series,
        'title': get_issue(number).title,
        'preview': render_issue(number),
        'receipt_status': getattr(receipt, 'status', None),
        'receipt_message_id': getattr(receipt, 'message_id', None),
    }


def eligible(user: User | None) -> bool:
    return bool(user and not user.is_blocked and not user.is_archived
                and user.application_status == ApplicationStatus.APPROVED)


async def _insert_setting(session: AsyncSession, *, key: str, value: dict, actor_id=None):
    # Reuse the existing JSON setting store and unique key; concurrent clicks
    # and workers cannot create duplicate progress/start records.
    if session.bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    await session.execute(insert(AppSetting).values(key=key, value=value, updated_by=actor_id)
                          .on_conflict_do_nothing(index_elements=['key']))


async def start(session: AsyncSession, *, actor: User | None = None) -> date:
    await _insert_setting(session, key='book_club_start_date',
                          value={'date': PROGRAM_START.isoformat()}, actor_id=actor.id if actor else None)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == 'book_club_start_date'))
    return date.fromisoformat(row.value['date'])


async def mark_progress(session: AsyncSession, user: User, number: int, kind: str) -> None:
    get_issue(number)
    if not eligible(user) or kind not in {'read', 'task'}:
        raise ValueError('Progress not allowed')
    await _insert_setting(session, key=f'bookclub:{user.id}:{kind}:{number}',
                          value={'at': datetime.now(ZoneInfo('Asia/Yerevan')).isoformat()}, actor_id=user.id)
    if kind == 'task':
        await add_points(
            session, user_id=user.id, points=5,
            reason=f'Литература ЭРА: задание к закону №{number}',
            approved_by=None, source_type='literature', source_id=number,
            idempotency_key=make_idempotency_key('literature', 'task', user.id, number),
        )
    await session.commit()


async def progress(session: AsyncSession, user: User) -> dict[str, int]:
    keys = (await session.scalars(select(AppSetting.key).where(
        AppSetting.key.like(f'bookclub:{user.id}:%')))).all()
    return {kind: sum(key.startswith(f'bookclub:{user.id}:{kind}:') for key in keys)
            for kind in ('read', 'task')}


async def save_reflection(session, user, number, answer):
    get_issue(number)
    if not eligible(user) or not answer.strip() or len(answer) > 3000:
        raise ValueError('Invalid reflection')
    key = f'book-reflection:{user.id}:{number}'
    value = {'answer': answer.strip(), 'at': datetime.now(ZoneInfo('Asia/Yerevan')).isoformat()}
    await _insert_setting(session, key=key, value=value, actor_id=user.id)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
    row.value = value
    await session.commit()


async def reflection_summary(session, user):
    rows = (await session.scalars(select(AppSetting).where(AppSetting.key.like(f'book-reflection:{user.id}:%')))).all()
    return sorted([(int(row.key.rsplit(':', 1)[1]), row.value['answer']) for row in rows])


async def daily_job(bot: Bot, settings: Settings, session_factory) -> None:
    if await run_editorial_queue(bot, settings, session_factory):
        return
    local_day = datetime.now(ZoneInfo('Asia/Yerevan')).date()
    candidate = publication_number(local_day)
    # Only today's calendar slot — never catch up missed days after downtime.
    if not settings.general_chat_id or candidate is None:
        return
    async with session_factory() as session:
        if not await series_issue_is_approved(
            session, local_day, settings.general_chat_id, candidate
        ):
            return
        start_day = await start(session)
        await session.commit()
        number = publication_number(local_day, start_day)
        if number is None or not await series_issue_is_approved(
            session, local_day, settings.general_chat_id, number
        ):
            return
        receipt = await series_issue_delivery(session, start_day, number)
        if receipt and receipt.status in {'uncertain', 'conflict'}:
            # Unknown prior result: do not retry until a human reconciles.
            return
        ids = (await session.scalars(select(User.id).where(
            User.book_club_subscribed.is_(True), User.is_blocked.is_(False),
            User.is_archived.is_(False), User.application_status == ApplicationStatus.APPROVED,
        ))).all()
    await send_general_topic(
        bot, settings, 'literature', render_issue(number),
        delivery_key=f'issue:{start_day.isoformat()}:{number}',
        parse_mode='HTML',
    )
    for user_id in ids:
        async with session_factory() as session:
            # Serialize against unsubscribe; no stale audience snapshot may send
            # after the opt-out transaction has completed.
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if not eligible(user) or not user.book_club_subscribed:
                continue
            from app.handlers.book_club import issue_keyboard
            await safe_send_once(
                bot, settings, user.telegram_id, render_issue(number),
                delivery_key=f'book-club:{start_day.isoformat()}:{number}:{user.id}',
                notification_type='book_club', parse_mode='HTML',
                reply_markup=issue_keyboard(number),
            )
            await session.commit()
        await asyncio.sleep(0.05)


# Editorial material shares the existing custom-content storage and sender.
# It never runs until an administrator explicitly enables this queue.
EDITORIAL_SETTINGS_KEY = 'book-club-editorial-settings'
# Editorial review approves a draft revision, not an arbitrary future scheduled
# public post. A dated scheduled send additionally requires exact authorization
# (code frozenset for tests; AppSetting for production editor actions).
APPROVED_SCHEDULED_EDITORIAL_PUBLICATIONS: frozenset[tuple[str, str, str]] = frozenset()
EDITORIAL_SCHEDULE_APPROVAL_PREFIX = 'literature-editorial-schedule:'


def scheduled_editorial_approval_key(
    on_date: date, chat_id: int | str, content_id: str, item_text: str
) -> tuple[str, str, str]:
    payload = {
        'topic': 'literature',
        'parse_mode': 'HTML',
        'content_id': content_id,
        'text': render_editorial(json.loads(item_text)),
    }
    digest = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')).hexdigest()
    return (on_date.isoformat(), str(chat_id), digest)


def editorial_schedule_setting_key(on_date: date, chat_id: int | str, content_id: str) -> str:
    return f'{EDITORIAL_SCHEDULE_APPROVAL_PREFIX}{on_date.isoformat()}:{chat_id}:{content_id}'


async def editorial_schedule_is_approved(
    session: AsyncSession,
    on_date: date,
    chat_id: int | str,
    content_id: str,
    item_text: str,
) -> bool:
    key = scheduled_editorial_approval_key(on_date, chat_id, content_id, item_text)
    if key in APPROVED_SCHEDULED_EDITORIAL_PUBLICATIONS:
        return True
    row = await session.scalar(select(AppSetting).where(
        AppSetting.key == editorial_schedule_setting_key(on_date, chat_id, content_id)
    ))
    if not row or not isinstance(row.value, dict) or row.value.get('revoked'):
        return False
    return row.value.get('digest') == key[2]


async def approve_editorial_schedule(
    session: AsyncSession,
    *,
    on_date: date,
    chat_id: int | str,
    content_id: str,
    item_text: str,
    actor_id: int,
) -> dict:
    day_key, chat_key, digest = scheduled_editorial_approval_key(
        on_date, chat_id, content_id, item_text
    )
    setting_key = editorial_schedule_setting_key(on_date, chat_id, content_id)
    await _insert_setting(session, key=setting_key, value={}, actor_id=actor_id)
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == setting_key).with_for_update()
        .execution_options(populate_existing=True)
    )
    value = {
        'date': day_key, 'chat_id': chat_key, 'content_id': content_id,
        'digest': digest, 'revoked': False,
        'approved_at': datetime.now(ZoneInfo('Asia/Yerevan')).isoformat(),
        'approved_by': actor_id,
    }
    row.value, row.updated_by = value, actor_id
    return value


EDITORIAL_FIELDS = {'Название': 'title', 'Автор': 'author', 'Введение': 'intro',
                    'Главная мысль': 'idea', 'Вопрос': 'question', 'Источник': 'source'}


def parse_editorial_text(text: str) -> dict[str, str]:
    fields, current = {}, None
    for line in text.strip().splitlines():
        label, _, value = line.partition(':')
        if label.strip() in EDITORIAL_FIELDS:
            current = EDITORIAL_FIELDS[label.strip()]
            fields[current] = value.strip()
        elif current:
            fields[current] += '\n' + line.strip()
    if any(not fields.get(key, '').strip() for key in ('title', 'author', 'intro', 'idea', 'question')):
        raise ValueError('required_editorial_fields')
    if len(fields['title']) > 180 or len(fields['author']) > 180 or len(render_editorial(fields).encode('utf-16-le')) // 2 > 3700:
        raise ValueError('editorial_text_too_long')
    return fields


def render_editorial(fields: dict) -> str:
    from html import escape
    text = (f"📚 <b>{escape(fields['title'])}</b>\n{escape(fields['author'])}\n\n"
            f"{escape(fields['intro'])}\n\n<b>Главная мысль</b>\n{escape(fields['idea'])}\n\n"
            f"💬 <b>Вопрос для обсуждения</b>\n{escape(fields['question'])}")
    if fields.get('source'):
        text += '\n\nИсточник: ' + escape(fields['source'])
    return text


def editorial_revision(item) -> str:
    import hashlib
    return hashlib.sha256(item.text.encode()).hexdigest()[:12]


async def editorial_settings(session: AsyncSession) -> dict:
    import json
    row = await session.scalar(select(AppSetting).where(AppSetting.key == EDITORIAL_SETTINGS_KEY))
    value = json.loads(row.value) if row and isinstance(row.value, str) else row.value if row else {}
    return {'enabled': False, 'paused': False, 'hour': 18, 'minute': 0, **value}


async def save_editorial_settings(session: AsyncSession, *, actor_id: int, **changes) -> dict:
    if set(changes) - {'enabled', 'paused', 'hour', 'minute'}:
        raise ValueError('invalid_editorial_settings')
    for key, maximum in (('hour', 23), ('minute', 59)):
        if key in changes and (type(changes[key]) is not int or not 0 <= changes[key] <= maximum):
            raise ValueError('invalid_editorial_time')
    from app.services.audit_service import audit
    await _insert_setting(session, key=EDITORIAL_SETTINGS_KEY, value={}, actor_id=actor_id)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == EDITORIAL_SETTINGS_KEY).with_for_update().execution_options(populate_existing=True))
    value = {**await editorial_settings(session), **changes}
    row.value, row.updated_by = value, actor_id
    await audit(session, actor_id=actor_id, action='literature.settings', entity_type='content', new_value=changes)
    return value


async def save_editorial_item(session: AsyncSession, text: str, *, actor_id: int, item_id: int | None = None):
    import json
    from uuid import uuid4
    from app.database.autocontent_models import GeneralCustomContent
    from app.database.system_models import NotificationDelivery
    from app.services.audit_service import audit
    fields = parse_editorial_text(text)
    item = await session.scalar(select(GeneralCustomContent).where(
        GeneralCustomContent.id == item_id, GeneralCustomContent.content_type == 'literature').with_for_update().execution_options(populate_existing=True)) if item_id else None
    if item_id:
        if item is None or await session.scalar(select(NotificationDelivery.id).where(
            NotificationDelivery.delivery_key == f'general-topic:literature:editorial:{item.content_id}')):
            raise ValueError('editorial_item_locked')
    else:
        item = GeneralCustomContent(content_id='literature-'+uuid4().hex, content_type='literature',
                                    date_key='queue', slot='evening', created_by=actor_id)
        session.add(item)
    item.title, item.text = fields['title'], json.dumps(fields, ensure_ascii=False)
    item.is_enabled, item.is_skipped, item.updated_by = False, False, actor_id
    await session.flush()
    await audit(session, actor_id=actor_id, action='literature.draft_saved', entity_type='content', entity_id=item.id)
    return item


async def approve_editorial_item(session: AsyncSession, item_id: int, revision: str, *, actor_id: int):
    from app.database.autocontent_models import GeneralCustomContent
    from app.services.audit_service import audit
    item = await session.scalar(select(GeneralCustomContent).where(
        GeneralCustomContent.id == item_id, GeneralCustomContent.content_type == 'literature').with_for_update().execution_options(populate_existing=True))
    if not item or item.is_skipped or editorial_revision(item) != revision:
        raise ValueError('editorial_item_changed')
    item.is_enabled, item.updated_by = True, actor_id
    await audit(session, actor_id=actor_id, action='literature.editor_approved', entity_type='content', entity_id=item.id,
                new_value={'revision': revision})
    return item


async def publish_editorial_item(
    bot, settings, session, item_id: int, revision: str, *,
    scheduled_on_date: date | None = None,
):
    import json
    from app.database.autocontent_models import GeneralCustomContent
    from app.services.general_topics_service import send_general_topic_once
    await _insert_setting(session, key=EDITORIAL_SETTINGS_KEY, value={})
    await session.scalar(select(AppSetting).where(AppSetting.key == EDITORIAL_SETTINGS_KEY).with_for_update().execution_options(populate_existing=True))
    item = await session.scalar(select(GeneralCustomContent).where(
        GeneralCustomContent.id == item_id, GeneralCustomContent.content_type == 'literature').with_for_update().execution_options(populate_existing=True))
    if not item or not item.is_enabled or editorial_revision(item) != revision:
        raise ValueError('editorial_item_not_approved')
    if scheduled_on_date is not None and not await editorial_schedule_is_approved(
        session, scheduled_on_date, settings.general_chat_id, item.content_id, item.text
    ):
        return 'approval_required'
    if item.is_skipped:
        return 'already_sent'
    topic = await session.scalar(select(AppSetting).where(
        AppSetting.key == f'general_forum:{settings.general_chat_id}:literature'))
    topic_value = json.loads(topic.value) if topic and isinstance(topic.value, str) else topic.value if topic else {}
    if not topic_value.get('thread_id'):
        return 'topic_missing'  # Never create/recreate a Telegram topic here.
    outcome = await send_general_topic_once(bot, settings, 'literature', render_editorial(json.loads(item.text)),
        delivery_key=f'editorial:{item.content_id}', parse_mode='HTML')
    if outcome.status == 'sent':
        recipients = list((await session.scalars(select(User.id).where(
            User.book_club_subscribed.is_(True), User.application_status == ApplicationStatus.APPROVED,
            User.is_blocked.is_(False), User.is_archived.is_(False)))).all())
        complete = True
        for user_id in recipients:
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update()
                                        .execution_options(populate_existing=True))
            if not eligible(user) or not user.book_club_subscribed:
                continue
            delivery = await safe_send_once(bot, settings, user.telegram_id, render_editorial(json.loads(item.text)),
                delivery_key=f'literature-editorial:{item.content_id}:{user.id}',
                notification_type='book_club', parse_mode='HTML')
            complete &= delivery.status in {'sent', 'uncertain', 'unreachable', 'blocked', 'skipped', 'conflict'}
        item.is_skipped = complete
    elif outcome.status in {'uncertain', 'conflict'} or (outcome.status == 'failed' and outcome.attempt_count >= 3):
        await save_editorial_settings(session, actor_id=item.updated_by or item.created_by, paused=True)
    return outcome.status


async def run_editorial_queue(bot, settings, session_factory, *, now=None) -> bool:
    import json
    from datetime import timezone
    from app.database.autocontent_models import GeneralCustomContent
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo('Europe/Moscow'))
    async with session_factory() as session:
        await session.scalar(select(AppSetting).where(AppSetting.key == EDITORIAL_SETTINGS_KEY).with_for_update()
                             .execution_options(populate_existing=True))
        config = await editorial_settings(session)
        if not config['enabled']:
            return False
        if config['paused'] or (now.hour, now.minute) < (config['hour'], config['minute']):
            return True
        day_key = f'book-club-editorial-day:{now.date().isoformat()}'
        if session.bind.dialect.name == 'postgresql':
            import hashlib
            from sqlalchemy import text
            lock = int.from_bytes(hashlib.sha256(day_key.encode()).digest()[:8], 'big', signed=True)
            await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock})
        day = await session.scalar(select(AppSetting).where(AppSetting.key == day_key).with_for_update())
        if day:
            value = json.loads(day.value) if isinstance(day.value, str) else day.value
            item = await session.get(GeneralCustomContent, value['item_id'])
        else:
            item = await session.scalar(select(GeneralCustomContent).where(
                GeneralCustomContent.content_type == 'literature', GeneralCustomContent.is_enabled.is_(True),
                GeneralCustomContent.is_skipped.is_(False)).order_by(GeneralCustomContent.id).limit(1))
        if item and item.is_enabled:
            publication_date = now.astimezone(ZoneInfo('Asia/Yerevan')).date()
            if not await editorial_schedule_is_approved(
                session, publication_date, settings.general_chat_id, item.content_id, item.text
            ):
                return True
            if not day:
                await _insert_setting(session, key=day_key, value={'item_id': item.id})
            await publish_editorial_item(
                bot, settings, session, item.id, editorial_revision(item),
                scheduled_on_date=publication_date,
            )
            await session.commit()
    return True


async def literature_stats(session: AsyncSession) -> dict[str, int]:
    """Count distinct participants using durable progress markers, not message views."""
    subscribed = await session.scalar(select(func.count(User.id)).where(
        User.book_club_subscribed.is_(True), User.is_blocked.is_(False),
        User.is_archived.is_(False), User.application_status == ApplicationStatus.APPROVED))
    keys = (await session.scalars(select(AppSetting.key).where(AppSetting.key.like('bookclub:%')))).all()
    readers, performers = set(), set()
    read_marks = task_marks = 0
    for key in keys:
        parts = key.split(':')
        if len(parts) != 4 or parts[2] not in {'read', 'task'}:
            continue
        if parts[2] == 'read':
            readers.add(parts[1]); read_marks += 1
        else:
            performers.add(parts[1]); task_marks += 1
    return {
        'subscribed': subscribed or 0, 'readers': len(readers),
        'performers': len(performers), 'active': len(readers | performers),
        'read_marks': read_marks, 'task_marks': task_marks,
    }


def format_literature_stats(stats: dict[str, int]) -> str:
    return (
        '📊 <b>ЭРА · Литературный клуб</b>\n\n'
        f'🔔 Подписаны: {stats["subscribed"]}\n'
        f'👥 Активны (отметили чтение или задание): {stats["active"]}\n'
        f'📖 Отметили чтение: {stats["readers"]}\n'
        f'📝 Выполнили задания: {stats["performers"]}\n'
        f'✅ Всего отметок чтения: {stats["read_marks"]}\n'
        f'⭐ Всего выполненных заданий: {stats["task_marks"]}\n\n'
        'Данные по отметкам участников в боте; просмотры постов и обсуждения не учитываются.'
    )
