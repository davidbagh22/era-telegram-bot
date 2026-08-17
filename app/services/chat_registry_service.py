"""Read-only registry for ERA Telegram workspaces and the public channel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AuditLog, ChatGreeting

CHAT_KEYS = ("general", "internal", "external", "leaders", "media", "era_channel")

CHAT_TITLES = {
    "general": "Общий чат",
    "internal": "Внутренние связи",
    "external": "Внешние связи",
    "leaders": "Чат лидеров",
    "media": "Медиа",
    "era_channel": "Канал ЭРА",
}

CHAT_PERMISSION_DESCRIPTIONS = {
    "general": "Все одобренные участники",
    "internal": "Участники направления «Внутренние связи» и админы",
    "external": "Участники направления «Внешние связи» и админы",
    "leaders": "Лидеры, руководители, совет и админы",
    "media": "Все одобренные участники — открытая рабочая точка входа в Медиа",
    "era_channel": "Бот-администратор с правом публикации",
}

AUDIT_LOOKBACK = 300


@dataclass(frozen=True)
class ChatRegistryEntry:
    chat_key: str
    title: str
    chat_id: int | None
    is_bound: bool
    permission_description: str
    greeting_enabled: bool | None
    last_sent_at: datetime | None
    last_error_at: datetime | None


@dataclass(frozen=True)
class ChatHealthResult:
    chat_key: str
    ok: bool
    detail: str


def _coerce_chat_id(value: int | str | None) -> int | None:
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    return int(text) if text.lstrip("-").isdigit() else None


def _chat_id_for_key(settings: Settings, chat_key: str) -> int | None:
    values: dict[str, int | str | None] = {
        "general": settings.general_chat_id,
        "internal": settings.internal_department_chat_id,
        "external": settings.external_department_chat_id,
        "leaders": settings.leaders_chat_id,
        "media": settings.media_chat_id,
        "era_channel": settings.era_channel_id,
    }
    return _coerce_chat_id(values.get(chat_key))


async def list_chat_registry(
    session: AsyncSession, settings: Settings
) -> list[ChatRegistryEntry]:
    greetings = {
        greeting.chat_key: greeting
        for greeting in (await session.scalars(select(ChatGreeting))).all()
    }
    recent_audit = (
        await session.scalars(
            select(AuditLog)
            .where(
                AuditLog.action.in_(("chat.broadcast_sent", "chat.broadcast_failed"))
            )
            .order_by(AuditLog.created_at.desc())
            .limit(AUDIT_LOOKBACK)
        )
    ).all()
    last_sent: dict[str, datetime] = {}
    last_error: dict[str, datetime] = {}
    for entry in recent_audit:
        chat_key = (entry.new_value or {}).get("chat")
        if chat_key not in CHAT_KEYS:
            continue
        if entry.action == "chat.broadcast_sent" and chat_key not in last_sent:
            last_sent[chat_key] = entry.created_at
        elif entry.action == "chat.broadcast_failed" and chat_key not in last_error:
            last_error[chat_key] = entry.created_at

    entries: list[ChatRegistryEntry] = []
    for chat_key in CHAT_KEYS:
        chat_id = _chat_id_for_key(settings, chat_key)
        greeting = greetings.get(chat_key)
        entries.append(
            ChatRegistryEntry(
                chat_key=chat_key,
                title=CHAT_TITLES[chat_key],
                chat_id=chat_id,
                is_bound=chat_id is not None,
                permission_description=CHAT_PERMISSION_DESCRIPTIONS[chat_key],
                greeting_enabled=(
                    greeting.is_enabled
                    if greeting is not None and chat_key != "era_channel"
                    else None
                ),
                last_sent_at=last_sent.get(chat_key),
                last_error_at=last_error.get(chat_key),
            )
        )
    return entries


async def check_chats_health(bot: Bot, settings: Settings) -> list[ChatHealthResult]:
    """Explicit read-only Telegram permission check; never sends a test post."""
    results: list[ChatHealthResult] = []
    for chat_key in CHAT_KEYS:
        chat_id = _chat_id_for_key(settings, chat_key)
        if chat_id is None:
            results.append(
                ChatHealthResult(chat_key=chat_key, ok=False, detail="not_bound")
            )
            continue
        try:
            member = await bot.get_chat_member(chat_id, bot.id)
        except TelegramAPIError as exc:
            results.append(
                ChatHealthResult(chat_key=chat_key, ok=False, detail=str(exc)[:200])
            )
            continue
        if member.status not in ("administrator", "creator"):
            results.append(
                ChatHealthResult(chat_key=chat_key, ok=False, detail="not_admin")
            )
            continue
        if chat_key == "era_channel" and member.status == "administrator":
            if not bool(getattr(member, "can_post_messages", False)):
                results.append(
                    ChatHealthResult(
                        chat_key=chat_key, ok=False, detail="cannot_post_messages"
                    )
                )
                continue
            can_edit = bool(getattr(member, "can_edit_messages", False))
            results.append(
                ChatHealthResult(
                    chat_key=chat_key,
                    ok=True,
                    detail="ok:post+edit" if can_edit else "ok:post",
                )
            )
            continue
        results.append(ChatHealthResult(chat_key=chat_key, ok=True, detail="ok"))
    return results
