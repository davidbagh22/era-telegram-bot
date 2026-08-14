"""Chat Infrastructure Registry — one screen answering "what state are our
4 org chats actually in" (2026-08 master spec, section 30). Read-only:
reuses chat_access_service.py (binding + the real access rules) and
admin_greetings_service.py (greeting state) rather than re-deriving either,
and reads "last send"/"last error" from the existing AuditLog trail
(chat.broadcast_sent / chat.broadcast_failed — the latter added alongside
this file so the registry has something real to show, not a placeholder).

check_chats_health() is the one thing here that talks to Telegram, and
only when explicitly called (the API endpoint is a POST an admin has to
press) -- it never runs on a schedule or on page load.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AuditLog, ChatGreeting

CHAT_KEYS = ("general", "internal", "external", "leaders")

CHAT_TITLES = {
    "general": "Общий чат",
    "internal": "Внутренние связи",
    "external": "Внешние связи",
    "leaders": "Чат лидеров",
}

# Mirrors the real rules in chat_access_service.py::check_chat_access() --
# kept as description text only (not re-implementing the logic), so this
# has to be read alongside that function if the rules ever change.
CHAT_PERMISSION_DESCRIPTIONS = {
    "general": "Все одобренные участники",
    "internal": "Участники направления «Внутренние связи» и админы",
    "external": "Участники направления «Внешние связи» и админы",
    "leaders": "Лидеры, руководители, совет и админы",
}

AUDIT_LOOKBACK = 200


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


def _chat_id_for_key(settings: Settings, chat_key: str) -> int | None:
    return {
        "general": settings.general_chat_id,
        "internal": settings.internal_department_chat_id,
        "external": settings.external_department_chat_id,
        "leaders": settings.leaders_chat_id,
    }.get(chat_key)


async def list_chat_registry(session: AsyncSession, settings: Settings) -> list[ChatRegistryEntry]:
    greetings = {
        g.chat_key: g
        for g in (await session.scalars(select(ChatGreeting))).all()
    }
    recent_audit = (
        await session.scalars(
            select(AuditLog)
            .where(AuditLog.action.in_(("chat.broadcast_sent", "chat.broadcast_failed")))
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

    entries = []
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
                greeting_enabled=greeting.is_enabled if greeting else None,
                last_sent_at=last_sent.get(chat_key),
                last_error_at=last_error.get(chat_key),
            )
        )
    return entries


async def check_chats_health(bot: Bot, settings: Settings) -> list[ChatHealthResult]:
    """Read-only Telegram check: can the bot still see each bound chat and
    is it still an administrator there (needed for greetings/moderation/
    broadcasts to keep working). Never writes anything -- purely reports."""
    results: list[ChatHealthResult] = []
    for chat_key in CHAT_KEYS:
        chat_id = _chat_id_for_key(settings, chat_key)
        if chat_id is None:
            results.append(ChatHealthResult(chat_key=chat_key, ok=False, detail="not_bound"))
            continue
        try:
            member = await bot.get_chat_member(chat_id, bot.id)
        except TelegramAPIError as exc:
            results.append(ChatHealthResult(chat_key=chat_key, ok=False, detail=str(exc)[:200]))
            continue
        if member.status not in ("administrator", "creator"):
            results.append(ChatHealthResult(chat_key=chat_key, ok=False, detail="not_admin"))
            continue
        results.append(ChatHealthResult(chat_key=chat_key, ok=True, detail="ok"))
    return results
