"""Existing opt-in club: durable progress, explicit consent, Yerevan schedule."""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.content.literature_issues import LAW_TITLES as LAW_TITLES, get_issue, render_issue
from app.database.models import AppSetting, User
from app.services.notification_service import safe_send_once
from app.utils.constants import ApplicationStatus

PROGRAM_START = date(2026, 10, 10)


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
    async with session_factory() as session:
        start_day = await start(session)
        await session.commit()
        day = (datetime.now(ZoneInfo('Asia/Yerevan')).date() - start_day).days
        if not 0 <= day < 48:
            return
        ids = (await session.scalars(select(User.id).where(
            User.book_club_subscribed.is_(True), User.is_blocked.is_(False),
            User.is_archived.is_(False), User.application_status == ApplicationStatus.APPROVED,
        ))).all()
    for user_id in ids:
        async with session_factory() as session:
            # Serialize against unsubscribe; no stale audience snapshot may send
            # after the opt-out transaction has completed.
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if not eligible(user) or not user.book_club_subscribed:
                continue
            from app.handlers.book_club import issue_keyboard
            await safe_send_once(
                bot, settings, user.telegram_id, render_issue(day + 1),
                delivery_key=f'book-club:{start_day.isoformat()}:{day}:{user.id}',
                notification_type='book_club', parse_mode='HTML',
                reply_markup=issue_keyboard(day + 1),
            )
            await session.commit()
        await asyncio.sleep(0.05)
