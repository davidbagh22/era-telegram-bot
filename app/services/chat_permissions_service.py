from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ChatPermissions
from sqlalchemy import select

from app.config import Settings
from app.database.models import User
from app.database.system_models import SystemIncident
from app.services.notification_service import notify_admins_once

logger = logging.getLogger(__name__)

_CHAT_PERMISSION_INCIDENT_KEY = "chat-permissions:general"
_PERMANENT_RETRY_AFTER = timedelta(hours=6)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def writable_permissions() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )


def _is_permanent_configuration_error(exc: TelegramAPIError) -> bool:
    return isinstance(exc, (TelegramBadRequest, TelegramForbiddenError))


async def _open_permission_incident(session_factory, exc: TelegramAPIError) -> int:
    now = _now()
    async with session_factory() as session:
        incident = await session.scalar(
            select(SystemIncident).where(SystemIncident.dedupe_key == _CHAT_PERMISSION_INCIDENT_KEY)
        )
        detail = f"Не удалось применить права общего чата: {exc.__class__.__name__}. Проверьте права бота и конфигурацию чата."
        if incident is None:
            incident = SystemIncident(
                dedupe_key=_CHAT_PERMISSION_INCIDENT_KEY,
                category="telegram_configuration",
                severity="high",
                status="open",
                title="Права общего чата",
                detail=detail,
                check_key="general_chat_permissions",
                occurrence_count=1,
                notification_generation=1,
                first_seen_at=now,
                last_seen_at=now,
                resolved_at=None,
                current_commit=None,
                last_healthy_commit=None,
                fix_prompt=None,
                admin_notified=False,
                recovery_notified=False,
            )
            session.add(incident)
            await session.flush()
        else:
            was_open = incident.status == "open"
            if not was_open:
                incident.notification_generation = max(1, incident.notification_generation) + 1
                incident.admin_notified = False
                incident.recovery_notified = False
                incident.first_seen_at = now
            incident.status = "open"
            incident.severity = "high"
            incident.title = "Права общего чата"
            incident.detail = detail
            incident.last_seen_at = now
            incident.resolved_at = None
            incident.occurrence_count += 1
        generation = max(1, incident.notification_generation)
        await session.commit()
        return generation


async def _resolve_permission_incident(session_factory) -> int | None:
    now = _now()
    async with session_factory() as session:
        incident = await session.scalar(
            select(SystemIncident).where(
                SystemIncident.dedupe_key == _CHAT_PERMISSION_INCIDENT_KEY,
                SystemIncident.status == "open",
            )
        )
        if incident is None:
            return None
        incident.status = "resolved"
        incident.resolved_at = now
        incident.last_seen_at = now
        generation = max(1, incident.notification_generation)
        await session.commit()
        return generation


async def _permission_backoff_active(session_factory) -> bool:
    async with session_factory() as session:
        incident = await session.scalar(
            select(SystemIncident).where(
                SystemIncident.dedupe_key == _CHAT_PERMISSION_INCIDENT_KEY,
                SystemIncident.status == "open",
            )
        )
        if incident is None:
            return False
        last_seen = incident.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        return _now() - last_seen < _PERMANENT_RETRY_AFTER


async def restore_general_chat_member(
    bot: Bot,
    settings: Settings,
    telegram_id: int,
) -> bool:
    """Repair a legacy per-user Telegram restriction in the general chat.

    Older versions of ERA could apply a personal `restrictChatMember` mute to
    people who had not completed registration yet. Changing the chat's default
    permissions does not remove that stored per-user override, and Telegram's
    Bot API cannot enumerate every historical member. This helper therefore
    repairs the exact person whenever we learn their Telegram id from a private
    interaction with the bot.

    Deliberately only touches `restricted` members. It never unbans kicked or
    banned users, so explicit moderation/admin decisions are not reversed.
    """
    chat_id = settings.general_chat_id
    if not chat_id:
        return False

    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=telegram_id)
        raw_status = getattr(member, "status", "")
        status = str(getattr(raw_status, "value", raw_status)).casefold()
        if status != "restricted":
            return False
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=telegram_id,
            permissions=writable_permissions(),
        )
        logger.info(
            "Restored legacy general-chat write permissions telegram_id=%s chat=%s",
            telegram_id,
            chat_id,
        )
        return True
    except TelegramAPIError:
        logger.warning(
            "Could not inspect/restore general-chat permissions telegram_id=%s chat=%s",
            telegram_id,
            chat_id,
            exc_info=True,
        )
        return False


async def enforce_general_chat_writable(bot: Bot, settings: Settings, session_factory) -> tuple[int, int]:
    """Restore writable defaults with durable backoff for permanent Telegram errors."""
    chat_id = settings.general_chat_id
    if not chat_id:
        return 0, 0

    if await _permission_backoff_active(session_factory):
        return 0, 1

    fixed = failed = 0
    try:
        await bot.set_chat_permissions(chat_id=chat_id, permissions=writable_permissions())
        fixed += 1
        recovered_generation = await _resolve_permission_incident(session_factory)
        if recovered_generation is not None:
            await notify_admins_once(
                bot,
                settings,
                "✅ ЭРА: права общего чата восстановлены. Проверка снова проходит успешно.",
                delivery_key=f"health:general_chat_permissions:{recovered_generation}:recovered",
                notification_type="system_incident_recovery",
            )
    except TelegramAPIError as exc:
        failed += 1
        if _is_permanent_configuration_error(exc):
            generation = await _open_permission_incident(session_factory, exc)
            logger.warning(
                "General-chat permissions have a permanent configuration error; retry backed off for %s hours",
                int(_PERMANENT_RETRY_AFTER.total_seconds() // 3600),
            )
            await notify_admins_once(
                bot,
                settings,
                "⚠️ ЭРА: не удалось применить права общего чата. Проверьте права бота и конфигурацию чата. Повторная проверка выполняется с backoff.",
                delivery_key=f"health:general_chat_permissions:{generation}:open",
                notification_type="system_incident",
            )
            return fixed, failed
        logger.warning("Transient error while setting general-chat permissions", exc_info=True)
        return fixed, failed

    async with session_factory() as session:
        telegram_ids = list((await session.scalars(select(User.telegram_id))).all())

    for telegram_id in telegram_ids:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=telegram_id)
            raw_status = getattr(member, "status", "")
            status = str(getattr(raw_status, "value", raw_status)).casefold()
            if status not in {"member", "administrator", "creator", "restricted"}:
                continue
            if status == "restricted":
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=telegram_id,
                    permissions=writable_permissions(),
                )
                fixed += 1
        except TelegramAPIError:
            continue
    return fixed, failed
