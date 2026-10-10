"""Existing opt-in club: durable progress, explicit consent, Yerevan schedule."""
from __future__ import annotations

import asyncio
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
def publication_number(on_date: date, start_date: date = PROGRAM_START) -> int | None:
    """One issue every calendar day for 48 days from the program start."""
    number = (on_date - start_date).days + 1
    return number if 1 <= number <= 48 else None


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


async def daily_job(bot: Bot, settings: Settings, session_factory) -> None:
    async with session_factory() as session:
        start_day = await start(session)
        await session.commit()
        number = publication_number(datetime.now(ZoneInfo('Asia/Yerevan')).date(), start_day)
        if number is None:
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
