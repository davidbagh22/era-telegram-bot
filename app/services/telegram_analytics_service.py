"""One source for Telegram screen/export facts. No invented pre-collection history."""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import Date, String, cast, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database.telegram_analytics import TelegramAnalyticsSource, TelegramMessageFact

logger = logging.getLogger(__name__)

CONTENT = ('text', 'caption', 'photo', 'video', 'animation', 'document', 'voice',
           'video_note', 'audio', 'sticker', 'poll', 'dice', 'contact', 'location',
           'venue', 'paid_media', 'story', 'game', 'checklist')


_coverage_gaps = {}
_checked_in_process = set()


def mark_coverage_gap(chat_id):
    _coverage_gaps[chat_id] = _coverage_gaps.get(chat_id, 0) + 1


async def persist_coverage_gap(session, chat_id):
    """Durable invalidation, visible to report requests in every worker."""
    mark_coverage_gap(chat_id)
    await session.execute(update(TelegramAnalyticsSource).where(TelegramAnalyticsSource.chat_id == chat_id).values(
        status='unverified', coverage_since=None, detail='observation_gap'))


def utc(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def source_targets(settings):
    targets = {}
    for kind, raw in [('channel', settings.era_channel_id), ('general', settings.general_chat_id)]:
        try:
            chat_id = int(raw)
        except (TypeError, ValueError):
            continue
        if chat_id:
            targets[kind] = chat_id
    return targets


def _insert(session, model):
    return (pg_insert if session.bind.dialect.name == 'postgresql' else sqlite_insert)(model)


async def observe_message(session, message, *, kind, observed_at=None):
    """Conflict-safe replay/edit handling. An album is one channel post, messages stay individual."""
    if not any(getattr(message, name, None) for name in CONTENT):
        return False
    if kind != 'channel':
        sender = message.from_user
        anonymous_admin = bool(message.sender_chat)
        if message.is_automatic_forward or (not anonymous_admin and (sender is None or sender.is_bot)):
            return False
    now = observed_at or datetime.now(timezone.utc)
    insert = _insert(session, TelegramMessageFact).values(
        chat_id=message.chat.id, message_id=message.message_id,
        media_group_id=message.media_group_id, topic_id=message.message_thread_id,
        published_at=utc(message.date), edited_at=utc(message.edit_date) if message.edit_date else None,
        observed_at=now, source_type='channel' if kind == 'channel' else 'human', deleted_state='unknown')
    # Telegram date/message id and album identity are immutable. Edits may arrive out of order.
    statement = insert.on_conflict_do_update(
        index_elements=['chat_id', 'message_id'],
        set_={'edited_at': insert.excluded.edited_at},
        where=(insert.excluded.edited_at.is_not(None) &
               (TelegramMessageFact.edited_at.is_(None) |
                (TelegramMessageFact.edited_at < insert.excluded.edited_at))))
    await session.execute(statement)
    src = _insert(session, TelegramAnalyticsSource).values(
        chat_id=message.chat.id, kind=kind, status='unverified', started_at=now,
        last_event_at=now, coverage_since=None, checked_at=None, detail='permissions_not_checked')
    await session.execute(src.on_conflict_do_update(index_elements=['chat_id'], set_={'last_event_at': now}))
    return True


async def refresh_sources(session, bot, settings, *, now=None):
    now = now or datetime.now(timezone.utc)
    if 'channel' not in source_targets(settings) and getattr(settings, 'era_channel_username', None):
        try:
            chat = await bot.get_chat('@' + settings.era_channel_username.removeprefix('@'))
            settings.era_channel_id = chat.id
        except Exception:
            pass
    acknowledgements = []
    for kind, chat_id in source_targets(settings).items():
        gap_version = _coverage_gaps.get(chat_id)
        first_check = chat_id not in _checked_in_process
        status, detail = 'collecting', None
        try:
            member = await bot.get_chat_member(chat_id, bot.id)
            if member.status not in ('administrator', 'creator'):
                if kind == 'general' and member.status == 'member':
                    me = await bot.get_me()
                    if not me.can_read_all_group_messages:
                        status, detail = 'limited', 'privacy_mode_limits_messages'
                else:
                    status, detail = 'unavailable', 'bot_is_not_administrator'
        except Exception:
            # Do not persist exception strings: they can contain URLs or sensitive metadata.
            status, detail = 'unavailable', 'telegram_permission_check_failed'
        row = await session.get(TelegramAnalyticsSource, chat_id)
        if row is None:
            row = TelegramAnalyticsSource(chat_id=chat_id, kind=kind, status=status, started_at=now)
            session.add(row)
        was_recent = row.checked_at is not None and utc(row.checked_at) >= now - timedelta(minutes=15)
        if status == 'collecting':
            if row.status != 'collecting' or not was_recent or row.coverage_since is None or gap_version is not None or first_check:
                row.coverage_since = now
        else:
            row.coverage_since = None
        row.status, row.detail, row.checked_at = status, detail, now
        await session.flush()
        acknowledgements.append((chat_id, gap_version))
    return acknowledgements


def confirm_sources_refresh(acknowledgements):
    # A flushed probe is not durable until the caller's commit succeeds.
    for chat_id, version in acknowledgements:
        _checked_in_process.add(chat_id)
        if _coverage_gaps.get(chat_id) == version:
            _coverage_gaps.pop(chat_id, None)


async def refresh_sources_job(bot, settings, session_factory):
    async with session_factory() as session:
        acknowledgements = await refresh_sources(session, bot, settings)
        await session.commit()
        confirm_sources_refresh(acknowledgements)
        # Operational evidence contains only source kind/state, never messages, users or credentials.
        for kind, chat_id in source_targets(settings).items():
            source = await session.get(TelegramAnalyticsSource, chat_id)
            logger.info('Telegram analytics source: kind=%s status=%s coverage_since=%s detail=%s',
                kind, source.status, source.coverage_since, source.detail)


def report_window(*, days=30, start_date=None, end_date=None, timezone_name='Asia/Yerevan', now=None):
    zone = ZoneInfo(timezone_name)
    today = (now or datetime.now(timezone.utc)).astimezone(zone).date()
    if (start_date is None) != (end_date is None):
        raise ValueError('both_dates_required')
    end = end_date or today
    start = start_date or end - timedelta(days=days - 1)
    if start > end or end > today or (end - start).days >= 366:
        raise ValueError('period_must_be_past_or_current_and_at_most_366_days')
    return (datetime.combine(start, datetime.min.time(), zone),
            datetime.combine(end + timedelta(days=1), datetime.min.time(), zone))


async def telegram_snapshot(session, settings, *, start, end, now=None):
    now = now or datetime.now(timezone.utc)
    zone = ZoneInfo(settings.timezone)
    duration = end - start
    previous_start = start - duration
    effective_end = min(utc(end), utc(now))
    previous_end = effective_end - duration
    result = {'timezone': settings.timezone, 'start': start.date().isoformat(), 'end': (end.date() - timedelta(days=1)).isoformat(),
              'updated_at': now.isoformat(), 'sources': []}
    for kind, title in [('channel', 'Публикации канала'), ('general', 'Сообщения общего чата')]:
        chat_id = source_targets(settings).get(kind)
        src = await session.get(TelegramAnalyticsSource, chat_id) if chat_id else None
        state = 'unavailable'
        coverage = utc(src.coverage_since) if src and src.coverage_since else None
        if src and src.status == 'collecting' and src.checked_at:
            state = ('stale' if utc(src.checked_at) < now - timedelta(minutes=15) else
                     'valid' if coverage and coverage <= utc(start) else 'insufficient')
        if chat_id in _coverage_gaps:
            state, coverage = 'insufficient', None
        # Grouping the first immutable album timestamp before filtering prevents midnight splits.
        identity = (func.coalesce(TelegramMessageFact.media_group_id,
                    literal('message:') + cast(TelegramMessageFact.message_id, String))
                    if kind == 'channel' else cast(TelegramMessageFact.message_id, String))
        query = (select(func.min(TelegramMessageFact.published_at).label('published_at'))
                 .where(TelegramMessageFact.chat_id == chat_id).group_by(identity)).subquery()
        timestamp = query.c.published_at
        total, observed, previous, latest = (await session.execute(select(
            func.count(), func.count().filter(timestamp >= utc(start), timestamp < effective_end),
            func.count().filter(timestamp >= utc(previous_start), timestamp < previous_end),
            func.max(timestamp)).select_from(query))).one()
        previous_valid = state == 'valid' and coverage is not None and coverage <= utc(previous_start)
        if session.bind.dialect.name == 'postgresql':
            local_day = cast(func.timezone(settings.timezone, timestamp), Date)
        else:
            offset = int(start.utcoffset().total_seconds() // 60)
            local_day = func.date(timestamp, f'{offset:+d} minutes')
        daily_counts = dict((await session.execute(select(local_day, func.count())
            .where(timestamp >= utc(start), timestamp < effective_end).group_by(local_day))).all())
        daily_counts = {str(key): value for key, value in daily_counts.items()}
        daily = []
        day = start.date()
        while day < end.date():
            day_start = datetime.combine(day, datetime.min.time(), zone)
            complete = state == 'valid' or (state == 'insufficient' and coverage and utc(day_start) >= coverage)
            count = daily_counts.get(day.isoformat(), 0)
            daily.append({'date': day.isoformat(), 'value': count if complete else None, 'observed': count})
            day += timedelta(days=1)
        result['sources'].append({
            'id': kind, 'label': title, 'data_state': state, 'value': observed if state == 'valid' else None,
            'observed_value': observed, 'unit': 'публикаций' if kind == 'channel' else 'сообщений',
            'previous_value': previous if previous_valid else None,
            'delta': observed - previous if previous_valid else None,
            'total_observed': total, 'started_at': src.started_at.isoformat() if src else None,
            'coverage_since': coverage.isoformat() if coverage else None,
            'last_event_at': src.last_event_at.isoformat() if src and src.last_event_at else None,
            'last_published_at': utc(latest).astimezone(zone).isoformat() if latest else None,
            'checked_at': src.checked_at.isoformat() if src and src.checked_at else None,
            'connection_status': src.status if src else 'not_connected', 'detail': src.detail if src else 'not_connected',
            'source': 'Telegram Bot API channel_post/edited_channel_post' if kind == 'channel' else 'Telegram Bot API message/edited_message',
            'explanation': ('Альбом — одна публикация; правки и повторы не увеличивают счётчик. Удаления неизвестны.' if kind == 'channel' else
                            'Все темы общего чата; без служебных сообщений, ботов и автоматических пересылок канала.'),
            'history_note': 'История до начала сбора не импортирована. Сегодня — по момент формирования; сравнение за равное прошедшее время. Частичный период не означает отсутствие активности.',
            'daily': daily})
    return result
