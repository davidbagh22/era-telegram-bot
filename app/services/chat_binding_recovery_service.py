from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.chat_moderation import PendingChatJoinRequest
from app.database.models import AppSetting, ChatGreeting, TaskDelivery

CHAT_BINDINGS = {
    "general": "general_chat_id",
    "internal": "internal_department_chat_id",
    "external": "external_department_chat_id",
    "leaders": "leaders_chat_id",
}


@dataclass(slots=True)
class ChatBindingRecoveryResult:
    recovered: dict[str, int]
    ambiguous: dict[str, list[int]]
    missing: list[str]


def choose_unique_chat_id(candidates: set[int]) -> int | None:
    return next(iter(candidates)) if len(candidates) == 1 else None


async def _candidate_ids(session: AsyncSession, chat_key: str) -> set[int]:
    candidates: set[int] = set()

    greeting_id = await session.scalar(
        select(ChatGreeting.chat_id).where(
            ChatGreeting.chat_key == chat_key,
            ChatGreeting.chat_id.is_not(None),
        )
    )
    if greeting_id is not None:
        candidates.add(int(greeting_id))

    delivered = (
        await session.scalars(
            select(TaskDelivery.chat_id)
            .where(TaskDelivery.chat_key == chat_key)
            .distinct()
            .limit(4)
        )
    ).all()
    candidates.update(int(item) for item in delivered if item is not None)

    pending = (
        await session.scalars(
            select(PendingChatJoinRequest.chat_id)
            .where(PendingChatJoinRequest.chat_key == chat_key)
            .distinct()
            .limit(4)
        )
    ).all()
    candidates.update(int(item) for item in pending if item is not None)
    return candidates


async def recover_chat_bindings(
    session: AsyncSession,
    settings: Settings,
) -> ChatBindingRecoveryResult:
    """Recover only bindings with one unambiguous historical Telegram ID.

    Invite links are deliberately not resolved. Conflicting historical IDs
    are surfaced as ambiguous instead of guessed.
    """
    recovered: dict[str, int] = {}
    ambiguous: dict[str, list[int]] = {}
    missing: list[str] = []

    for chat_key, setting_key in CHAT_BINDINGS.items():
        configured = getattr(settings, setting_key)
        if configured:
            continue
        candidates = await _candidate_ids(session, chat_key)
        chat_id = choose_unique_chat_id(candidates)
        if chat_id is None:
            if candidates:
                ambiguous[chat_key] = sorted(candidates)
            else:
                missing.append(chat_key)
            continue

        setattr(settings, setting_key, chat_id)
        row = await session.scalar(select(AppSetting).where(AppSetting.key == setting_key))
        if row is None:
            session.add(AppSetting(key=setting_key, value=chat_id, updated_by=None))
        else:
            row.value = chat_id
        greeting = await session.scalar(
            select(ChatGreeting).where(ChatGreeting.chat_key == chat_key)
        )
        if greeting is not None:
            greeting.chat_id = chat_id
        recovered[chat_key] = chat_id

    if recovered:
        await session.commit()
    return ChatBindingRecoveryResult(
        recovered=recovered,
        ambiguous=ambiguous,
        missing=missing,
    )
