"""Personal-message and chat broadcasts — shared by the bot's "📨 Рассылка в
личные сообщения" and "📣 Сообщение в выбранные чаты" flows
(app/handlers/admin/panel.py, app/handlers/admin/management_ready.py) and
the Mini App's admin tools. See app/services/admin_goals_service.py for why
this is extracted.

Chat binding itself (attaching a Telegram chat_id to a chat_key via a
forwarded message) stays bot-only by design — Telegram only exposes a
chat's id through a message actually sent in it, which a web form can't
replicate. This service only sends to chats that are already bound.
"""

from __future__ import annotations

import asyncio
import hashlib
from uuid import uuid4
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Broadcast, Department, Direction, User, UserDepartment, UserDirection
from app.services.audit_service import audit
from app.services.notification_service import BroadcastResult, BroadcastFailure, safe_send, safe_send_once
from app.services.general_topics_service import send_general_topic
from app.utils.constants import ApplicationStatus

AUDIENCE_TYPES = {"all", "role", "department", "direction", "age", "city"}
ROLE_FILTER_VALUES = {"participant", "activist", "leader", "head", "council"}
AGE_RANGES: dict[str, tuple[int, int]] = {
    "14_17": (14, 17),
    "18_24": (18, 24),
    "25_34": (25, 34),
    "35_plus": (35, 200),
}
CHAT_KEYS = {"general", "internal", "external", "leaders"}
MAX_TEXT_LENGTH = 3500
SURVEY_CHAT_MARKER = "[[era-survey]]"
CONFERENCE_SPEAKERS_PAYLOAD = "conference_speakers"


class BroadcastError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class AudienceOption:
    value: str
    label: str


async def department_options(session: AsyncSession) -> list[AudienceOption]:
    departments = (await session.scalars(select(Department).order_by(Department.name))).all()
    return [AudienceOption(value=str(d.id), label=d.name) for d in departments]


async def direction_options(session: AsyncSession) -> list[AudienceOption]:
    directions = (await session.scalars(select(Direction).order_by(Direction.name))).all()
    return [AudienceOption(value=str(d.id), label=d.name) for d in directions]


def _parse_id(filter_value: str | None) -> int:
    if not filter_value:
        raise BroadcastError("filter_required")
    try:
        return int(filter_value)
    except ValueError as exc:
        raise BroadcastError("invalid_filter") from exc


async def _resolve_recipients(
    session: AsyncSession, audience: str, filter_value: str | None
) -> list[User]:
    if audience not in AUDIENCE_TYPES:
        raise BroadcastError("invalid_audience")
    query = select(User).where(
        User.application_status == ApplicationStatus.APPROVED,
        User.is_blocked.is_(False),
        User.is_archived.is_(False),
    )
    if audience == "role":
        if filter_value not in ROLE_FILTER_VALUES:
            raise BroadcastError("invalid_filter")
        query = query.where(User.role == filter_value)
    elif audience == "department":
        query = query.join(UserDepartment).where(UserDepartment.department_id == _parse_id(filter_value))
    elif audience == "direction":
        query = query.join(UserDirection).where(UserDirection.direction_id == _parse_id(filter_value))
    elif audience == "city":
        if not filter_value or not filter_value.strip():
            raise BroadcastError("filter_required")
        query = query.where(func.lower(User.city) == filter_value.strip().lower())
    elif audience == "age":
        if filter_value not in AGE_RANGES:
            raise BroadcastError("invalid_filter")
        low, high = AGE_RANGES[filter_value]
        query = query.where(User.age.between(low, high))
    return list((await session.scalars(query)).unique().all())


async def preview_recipient_count(session: AsyncSession, audience: str, filter_value: str | None) -> int:
    return len(await _resolve_recipients(session, audience, filter_value))


async def _deliver_campaign(bot, settings, session, item) -> BroadcastResult:
    metadata = item.audience_filter_json
    result = BroadcastResult()
    needs_review = False
    retry = False
    for user_id in metadata.get("recipient_ids", []):
        recipient = await session.scalar(select(User).where(User.id == user_id)
                                         .execution_options(populate_existing=True))
        if recipient is None or recipient.is_archived or recipient.is_blocked or recipient.application_status != ApplicationStatus.APPROVED:
            continue
        result.total += 1
        delivery = await safe_send_once(
            bot, settings, recipient.telegram_id, item.text,
            delivery_key=f"admin-campaign:{item.id}:user:{recipient.id}",
            notification_type="admin_broadcast",
        )
        result.duplicates += int(delivery.duplicate)
        if delivery.sent:
            result.sent += 1
        else:
            result.failed += 1
            temporary = delivery.error_code in {"telegram_retry_after", "delivery_ledger_unavailable", "delivery_in_flight", "delivery_retry_ledger_failed"}
            retry |= temporary
            needs_review |= delivery.status in {"uncertain", "conflict"}
            result.failures.append(BroadcastFailure(recipient.telegram_id, delivery.error_code or delivery.status, temporary))
        await asyncio.sleep(0.05)
    if item.audience_type == "all" and settings.general_chat_id:
        ok = await send_general_topic(bot, settings, "notifications", item.text,
                                      delivery_key=f"broadcast:{item.id}")
        if not ok:
            needs_review = True
    item.status = "sending" if retry else ("review_required" if needs_review else ("partial" if result.failed else "sent"))
    if item.status == "sent":
        item.sent_at = datetime.now().astimezone()
    await audit(session, actor_id=item.author_id, action="broadcast.delivery",
                entity_type="broadcast", entity_id=item.id,
                new_value={"sent": result.sent, "failed": result.failed, "duplicates": result.duplicates, "status": item.status})
    await session.commit()
    return result


async def send_personal_broadcast(
    bot: Bot, session: AsyncSession, *, audience: str, filter_value: str | None,
    text: str, author_id: int | None, settings: Settings | None = None,
    campaign_key: str | None = None,
) -> BroadcastResult:
    text = text.strip()[:MAX_TEXT_LENGTH]
    if not text:
        raise BroadcastError("text_required")
    if settings is None:
        raise BroadcastError("settings_required")
    recipients = await _resolve_recipients(session, audience, filter_value)
    # Scope caller-generated confirmation keys to the authenticated author.
    key = hashlib.sha256(f"{author_id}:{campaign_key or uuid4()}".encode()).hexdigest()
    if session.bind.dialect.name == "postgresql":
        lock = int.from_bytes(bytes.fromhex(key)[:8], "big", signed=True)
        await session.execute(sql_text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    item = await session.scalar(select(Broadcast).where(
        Broadcast.audience_filter_json["campaign_key"].as_string() == key))
    if item is None:
        item = Broadcast(title="Рассылка ЭРА", text=text, audience_type=audience,
                         audience_filter_json={"value": filter_value, "campaign_key": key,
                                               "recipient_ids": [u.id for u in recipients]},
                         author_id=author_id, status="sending")
        session.add(item)
        await session.flush()
    elif item.text != text or item.audience_type != audience or item.audience_filter_json.get("value") != filter_value:
        raise BroadcastError("campaign_key_conflict")
    # The durable campaign and fixed audience exist before the first Telegram call.
    # A worker can resume after a process crash without starting a new campaign.
    await session.commit()
    return await _deliver_campaign(bot, settings, session, item)


async def resume_broadcasts(bot, settings, session_factory):
    async with session_factory() as session:
        campaigns = (await session.scalars(select(Broadcast).where(Broadcast.status == "sending")
                                           .order_by(Broadcast.id).limit(5))).all()
        for item in campaigns:
            if "campaign_key" in (item.audience_filter_json or {}):
                await _deliver_campaign(bot, settings, session, item)


async def _survey_chat_keyboard(bot: Bot) -> InlineKeyboardMarkup:
    bot_user = await bot.get_me()
    username = (bot_user.username or "").lstrip("@").strip()
    if not username:
        raise BroadcastError("bot_username_unavailable")
    url = f"https://t.me/{username}?start={CONFERENCE_SPEAKERS_PAYLOAD}"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Выбрать спикеров", url=url)]]
    )


async def send_chat_broadcast(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    *,
    chat_key: str,
    text: str,
    actor_id: int | None,
) -> None:
    if chat_key not in CHAT_KEYS:
        raise BroadcastError("invalid_chat")
    with_survey_button = SURVEY_CHAT_MARKER in text
    text = text.replace(SURVEY_CHAT_MARKER, "").strip()[:MAX_TEXT_LENGTH]
    if not text:
        raise BroadcastError("text_required")
    chat_ids = {
        "general": settings.general_chat_id,
        "internal": settings.internal_department_chat_id,
        "external": settings.external_department_chat_id,
        "leaders": settings.leaders_chat_id,
    }
    chat_id = chat_ids.get(chat_key)
    if not chat_id:
        raise BroadcastError("chat_not_bound")
    reply_markup = await _survey_chat_keyboard(bot) if with_survey_button else None
    if chat_key == "general":
        ok = await send_general_topic(bot, settings, "notifications", text, reply_markup=reply_markup)
    else:
        ok = await safe_send(bot, chat_id, text, reply_markup)
    if not ok:
        await audit(
            session,
            actor_id=actor_id,
            action="chat.broadcast_failed",
            entity_type="chat",
            entity_id=None,
            new_value={"chat": chat_key, "survey_button": with_survey_button},
        )
        raise BroadcastError("delivery_failed")
    await audit(
        session,
        actor_id=actor_id,
        action="chat.broadcast_sent",
        entity_type="chat",
        entity_id=None,
        new_value={"chat": chat_key, "survey_button": with_survey_button},
    )
