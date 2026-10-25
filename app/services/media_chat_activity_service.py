from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.media_models import MediaChatActivity

# DELTA ToR §39: what counts as a human message worth tracking.


def is_human_content_message(message: Message) -> bool:
    if message.from_user is None or message.from_user.is_bot:
        return False
    # Service events (join/leave/pin/title change/...) never carry real
    # content -- text/caption/media presence is what distinguishes an
    # actual contribution from Telegram's own chat-membership noise.
    return bool(
        message.text
        or message.caption
        or message.photo
        or message.video
        or message.document
        or message.voice
        or message.video_note
        or message.audio
        or message.sticker
    )


async def record_media_chat_message(
    session: AsyncSession, *, chat_id: int, telegram_user_id: int, when: datetime | None = None
) -> None:
    """DELTA ToR §38-40: idempotent-per-call daily counter bump. Never
    stores message text -- only today's row gets +1 to human_messages and
    the author id added to a same-day dedup set for unique_authors."""
    today = (when or datetime.now(timezone.utc)).date()
    row = await session.scalar(
        select(MediaChatActivity).where(
            MediaChatActivity.chat_id == chat_id, MediaChatActivity.activity_date == today
        )
    )
    if row is None:
        row = MediaChatActivity(chat_id=chat_id, activity_date=today, human_messages=0, author_ids_json=[])
        session.add(row)
    row.human_messages += 1
    if telegram_user_id not in row.author_ids_json:
        row.author_ids_json = [*row.author_ids_json, telegram_user_id]
    await session.commit()


@dataclass(frozen=True)
class ChatActivityWindow:
    messages: int
    active_authors: int


@dataclass(frozen=True)
class ChatActivitySummary:
    messages_7d: int
    messages_30d: int
    active_authors_7d: int
    active_authors_30d: int
    trend_vs_previous_period: float | None  # +0.12 == +12%, None if no prior-period baseline


async def _window(session: AsyncSession, chat_id: int, *, start: date, end: date) -> ChatActivityWindow:
    rows = list(
        (
            await session.scalars(
                select(MediaChatActivity).where(
                    MediaChatActivity.chat_id == chat_id,
                    MediaChatActivity.activity_date >= start,
                    MediaChatActivity.activity_date < end,
                )
            )
        ).all()
    )
    messages = sum(row.human_messages for row in rows)
    authors: set[int] = set()
    for row in rows:
        authors.update(row.author_ids_json or [])
    return ChatActivityWindow(messages=messages, active_authors=len(authors))


async def chat_activity_summary(
    session: AsyncSession, chat_id: int, *, now: datetime | None = None
) -> ChatActivitySummary:
    """DELTA ToR §38 contract: messages_7d/30d, active_authors_7d/30d,
    trend_vs_previous_period (the 30d window compared to the 30d window
    immediately before it)."""
    today = (now or datetime.now(timezone.utc)).date() + timedelta(days=1)  # end is exclusive
    last_7 = await _window(session, chat_id, start=today - timedelta(days=7), end=today)
    last_30 = await _window(session, chat_id, start=today - timedelta(days=30), end=today)
    previous_30 = await _window(session, chat_id, start=today - timedelta(days=60), end=today - timedelta(days=30))

    trend: float | None = None
    if previous_30.messages > 0:
        trend = (last_30.messages - previous_30.messages) / previous_30.messages

    return ChatActivitySummary(
        messages_7d=last_7.messages,
        messages_30d=last_30.messages,
        active_authors_7d=last_7.active_authors,
        active_authors_30d=last_30.active_authors,
        trend_vs_previous_period=trend,
    )
