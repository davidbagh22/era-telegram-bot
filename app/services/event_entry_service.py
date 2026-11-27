"""Durable "which event did this person come for" memory for newcomers.

A person who opens an event from a channel, topic, project card, afisha or the
Mini App before their application is approved must come back to that event
after registration and approval. The choice is keyed by Telegram ID (a user row
may not exist yet) and stored in ``app_settings`` so it survives restarts and FSM
resets. It never grants access: the event card is always re-checked on open.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AppSetting, Event
from app.services.event_service import PUBLIC_EVENT_STATUSES

logger = logging.getLogger(__name__)

KEY_PREFIX = "event-entry:"
INTENT_TTL = timedelta(days=30)


def intent_key(telegram_id: int) -> str:
    return f"{KEY_PREFIX}{int(telegram_id)}"


def _parse(value: object) -> tuple[int | None, datetime | None]:
    if not isinstance(value, dict):
        return None, None
    raw_id = value.get("event_id")
    event_id = raw_id if isinstance(raw_id, int) and not isinstance(raw_id, bool) and 0 < raw_id <= 2_147_483_647 else None
    try:
        saved_at = datetime.fromisoformat(str(value.get("saved_at")))
    except ValueError:
        saved_at = None
    if saved_at is not None and saved_at.tzinfo is None:
        saved_at = saved_at.replace(tzinfo=timezone.utc)
    return event_id, saved_at


async def remember_event(session: AsyncSession, telegram_id: int, event_id: int) -> None:
    """Upsert the single pending event for this Telegram account."""
    value = {"event_id": int(event_id), "saved_at": datetime.now(timezone.utc).isoformat()}
    key = intent_key(telegram_id)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
    if row is not None:
        row.value = value
        return
    try:
        async with session.begin_nested():
            session.add(AppSetting(key=key, value=value))
            await session.flush()
    except IntegrityError:
        row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
        if row is not None:
            row.value = value


async def remembered_event_id(session: AsyncSession, telegram_id: int, *, now: datetime | None = None) -> int | None:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == intent_key(telegram_id)))
    if row is None:
        return None
    event_id, saved_at = _parse(row.value)
    current = now or datetime.now(timezone.utc)
    if event_id is None or saved_at is None or current - saved_at > INTENT_TTL:
        return None
    return event_id


async def forget_event(session: AsyncSession, telegram_id: int, event_id: int | None = None) -> None:
    """Drop the pending event. With ``event_id`` only the matching one is dropped."""
    row = await session.scalar(select(AppSetting).where(AppSetting.key == intent_key(telegram_id)))
    if row is None:
        return
    if event_id is not None and _parse(row.value)[0] != event_id:
        return
    await session.delete(row)


async def pending_public_event(session: AsyncSession, telegram_id: int) -> Event | None:
    """The remembered event, only while it is still publicly openable."""
    event_id = await remembered_event_id(session, telegram_id)
    if event_id is None:
        return None
    event = await session.get(Event, event_id)
    if event is None or event.status not in PUBLIC_EVENT_STATUSES:
        return None
    return event


def event_button(event: Event) -> InlineKeyboardButton:
    title = " ".join(str(event.title).split())
    label = f"🎟 К мероприятию «{title[:36]}»"
    return InlineKeyboardButton(text=label, callback_data=f"event:view:{event.id}")


def with_event_button(markup: InlineKeyboardMarkup | None, event: Event | None) -> InlineKeyboardMarkup | None:
    if event is None:
        return markup
    rows = [[event_button(event)]]
    if markup is not None:
        rows.extend(list(row) for row in markup.inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def with_pending_event_button(
    session: AsyncSession, telegram_id: int, markup: InlineKeyboardMarkup | None
) -> InlineKeyboardMarkup | None:
    """Best-effort: a lookup problem must never block an approval notice."""
    try:
        return with_event_button(markup, await pending_public_event(session, telegram_id))
    except Exception:
        logger.exception("Could not attach the pending event button")
        return markup


async def registration_followup(
    session: AsyncSession, telegram_id: int, *, approved: bool
) -> tuple[str, InlineKeyboardMarkup | None] | None:
    """Message shown right after the application is saved, if an event is waiting."""
    try:
        event = await pending_public_event(session, telegram_id)
    except Exception:
        logger.exception("Could not read the pending event after registration")
        return None
    if event is None:
        return None
    title = " ".join(str(event.title).split())
    if approved:
        return f"Вы пришли на мероприятие «{title}». Откройте карточку и займите место.", with_event_button(None, event)
    return (
        f"Мероприятие «{title}» мы запомнили. Как только заявку одобрят, "
        "бот пришлёт кнопку, чтобы сразу вернуться к записи.",
        None,
    )
