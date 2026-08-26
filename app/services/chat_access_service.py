from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import ChatPermissions
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.chat_moderation import PendingChatJoinRequest
from app.database.models import User
from app.services.audit_service import audit
from app.services.referral_service import award_registration_referral
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role

logger = logging.getLogger(__name__)
CHAT_SETTING_KEYS = {"general": "general_chat_id", "internal": "internal_department_chat_id", "external": "external_department_chat_id", "leaders": "leaders_chat_id", "media": "media_chat_id"}
PENDING_REASONS = {"not_registered", "not_approved"}

@dataclass(frozen=True)
class ChatAccessDecision:
    allowed: bool
    chat_key: str | None
    reason: str
    pending: bool = False

def writable_permissions() -> ChatPermissions:
    return ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)

def restricted_permissions() -> ChatPermissions:
    return ChatPermissions(can_send_messages=False, can_send_audios=False, can_send_documents=False, can_send_photos=False, can_send_videos=False, can_send_video_notes=False, can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False, can_add_web_page_previews=False)

def chat_key_for_id(settings: Settings, chat_id: int) -> str | None:
    for chat_key, setting_key in CHAT_SETTING_KEYS.items():
        if getattr(settings, setting_key, None) == chat_id:
            return chat_key
    return None

def _has_department(user: User, marker: str) -> bool:
    marker = marker.casefold()
    return any(marker in link.department.name.casefold() for link in user.departments)

def _has_media_membership(user: User) -> bool:
    for link in getattr(user, "directions", None) or []:
        direction = getattr(link, "direction", None)
        if direction is None or str(getattr(direction, "name", "")).casefold() != "медиа":
            continue
        if getattr(direction, "leader_id", None) == user.id:
            return True
        return str(getattr(link, "status", "")).casefold() == "approved"
    return False

def check_chat_access(user: User | None, chat_key: str | None) -> ChatAccessDecision:
    if chat_key is None:
        return ChatAccessDecision(True, None, "unmanaged_chat")
    if user is None:
        return ChatAccessDecision(False, chat_key, "not_registered", pending=True)
    if user.is_blocked:
        return ChatAccessDecision(False, chat_key, "blocked")
    if user.is_archived:
        return ChatAccessDecision(False, chat_key, "archived")
    if user.application_status == ApplicationStatus.REJECTED:
        return ChatAccessDecision(False, chat_key, "rejected")
    if user.application_status != ApplicationStatus.APPROVED:
        return ChatAccessDecision(False, chat_key, "not_approved", pending=True)
    if user.role == Role.ADMIN:
        return ChatAccessDecision(True, chat_key, "approved")
    if chat_key == "general":
        return ChatAccessDecision(True, chat_key, "approved")
    if chat_key == "media":
        allowed = _has_media_membership(user)
        return ChatAccessDecision(allowed, chat_key, "approved" if allowed else "media_approval_required")
    if chat_key == "internal":
        allowed = _has_department(user, "внутрен")
        return ChatAccessDecision(allowed, chat_key, "approved" if allowed else "wrong_department")
    if chat_key == "external":
        allowed = _has_department(user, "внешн")
        return ChatAccessDecision(allowed, chat_key, "approved" if allowed else "wrong_department")
    if chat_key == "leaders":
        allowed = user.role in PRIVILEGED_ROLES
        return ChatAccessDecision(allowed, chat_key, "approved" if allowed else "wrong_role")
    return ChatAccessDecision(False, chat_key, "unknown_chat")

def access_message(reason: str) -> str:
    messages = {"not_registered": "Чтобы вступить в чат ЭРА, сначала пройдите регистрацию в боте.", "not_approved": "Регистрация получена. Дождитесь подтверждения администратора.", "blocked": "Доступ к чатам ЭРА временно закрыт. Если это ошибка, напишите администратору.", "archived": "Доступ к чатам ЭРА закрыт, потому что профиль находится в архиве.", "rejected": "Заявка в ЭРА не одобрена, поэтому доступ к закрытым чатам не открыт.", "wrong_department": "Этот чат доступен только участникам соответствующего направления ЭРА.", "wrong_role": "Этот чат доступен только лидерам и команде ЭРА.", "media_approval_required": "Media Chat доступен только участникам, которых одобрил руководитель Медиа.", "unknown_chat": "Этот чат не найден в настройках доступа ЭРА."}
    return messages.get(reason, "Доступ к этому чату пока не открыт.")

async def remember_join_request(session: AsyncSession, *, chat_id: int, user_id: int, chat_key: str, reason: str) -> None:
    current = await session.scalar(select(PendingChatJoinRequest).where(PendingChatJoinRequest.chat_id == chat_id, PendingChatJoinRequest.user_id == user_id))
    if current:
        current.chat_key, current.status, current.reason = chat_key, "pending", reason
    else:
        session.add(PendingChatJoinRequest(chat_id=chat_id, user_id=user_id, chat_key=chat_key, status="pending", reason=reason))

async def close_join_request(session: AsyncSession, *, chat_id: int, user_id: int, status: str, reason: str) -> None:
    current = await session.scalar(select(PendingChatJoinRequest).where(PendingChatJoinRequest.chat_id == chat_id, PendingChatJoinRequest.user_id == user_id))
    if current:
        current.status, current.reason = status, reason

async def approve_join_request(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        await bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
        return True
    except TelegramAPIError:
        logger.exception("Could not approve join request chat=%s user=%s", chat_id, user_id)
        return False

async def decline_join_request(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        await bot.decline_chat_join_request(chat_id=chat_id, user_id=user_id)
        return True
    except TelegramAPIError:
        logger.exception("Could not decline join request chat=%s user=%s", chat_id, user_id)
        return False

async def restrict_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        await bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=restricted_permissions())
        return True
    except TelegramAPIError:
        logger.exception("Could not restrict member chat=%s user=%s", chat_id, user_id)
        return False

async def unrestrict_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        await bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=writable_permissions())
        return True
    except TelegramAPIError:
        logger.exception("Could not unrestrict member chat=%s user=%s", chat_id, user_id)
        return False

async def remove_rejected_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Legacy helper kept for compatibility; chat sync no longer removes rejected users."""
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        return True
    except TelegramAPIError:
        logger.exception("Could not remove rejected member chat=%s user=%s", chat_id, user_id)
        return False

async def notify_user(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except TelegramForbiddenError:
        return
    except TelegramAPIError:
        logger.exception("Could not notify user %s about chat access", user_id)

async def sync_user_chat_access(bot: Bot, settings: Settings, session: AsyncSession, user: User) -> tuple[int, int]:
    fixed = failed = 0
    pending = (await session.scalars(select(PendingChatJoinRequest).where(PendingChatJoinRequest.user_id == user.telegram_id, PendingChatJoinRequest.status == "pending"))).all()
    for item in pending:
        decision = check_chat_access(user, item.chat_key)
        if not decision.allowed:
            item.reason = decision.reason
            if not decision.pending:
                if await decline_join_request(bot, item.chat_id, item.user_id):
                    item.status = "declined"; fixed += 1
                else:
                    failed += 1
            continue
        if await approve_join_request(bot, item.chat_id, item.user_id):
            item.status = "approved"; item.reason = "approved"; fixed += 1
            if item.chat_key == "general":
                await award_registration_referral(session, invitee_user_id=user.id)
        else:
            failed += 1

    # Once a person is in a chat, registration/application/role/department
    # status never controls their ability to write. Join-request checks remain
    # intact for entry to managed chats.
    for chat_id in settings.chat_ids:
        chat_key = chat_key_for_id(settings, chat_id)
        decision = check_chat_access(user, chat_key)
        ok = await unrestrict_member(bot, chat_id, user.telegram_id)
        fixed += int(ok)
        failed += int(not ok)
        if ok and decision.allowed and chat_key == "general":
            await award_registration_referral(session, invitee_user_id=user.id)

    if fixed or failed:
        await audit(session, actor_id=user.id, action="chat_access.synced", entity_type="user", entity_id=user.id, new_value={"telegram_id": user.telegram_id, "fixed": fixed, "failed": failed})
    return fixed, failed
