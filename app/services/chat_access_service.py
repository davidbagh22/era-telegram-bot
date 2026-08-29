from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import (
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.chat_moderation import PendingChatJoinRequest
from app.database.models import User
from app.database.system_models import NotificationDelivery
from app.services.audit_service import audit
from app.services.referral_service import award_registration_referral
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role

logger = logging.getLogger(__name__)
CHAT_SETTING_KEYS = {
    "general": "general_chat_id",
    "internal": "internal_department_chat_id",
    "external": "external_department_chat_id",
    "leaders": "leaders_chat_id",
    "media": "media_chat_id",
}
PENDING_REASONS = {"not_registered", "not_approved"}

GENERAL_REGISTRATION_PIN_KEY = "general-registration-pin-v2"
GENERAL_REGISTRATION_PIN_TEXT = (
    "<b>ЭРА теперь в одном боте.</b>\n\n"
    "Мероприятия, личное портфолио, сертификаты, баллы за активность, "
    "возможности от партнёров и инструменты для развития — теперь всё в одном месте.\n\n"
    "Регистрация занимает пару минут. Дальше твоя активность начинает работать на тебя.\n\n"
    "👇 <b>Нажми «Начать» и зарегистрируйся в ЭРА</b>"
)
GENERAL_REGISTRATION_START_URL = "https://t.me/ERA_1bot?start=community"


@dataclass(frozen=True)
class ChatAccessDecision:
    allowed: bool
    chat_key: str | None
    reason: str
    pending: bool = False


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
        return ChatAccessDecision(
            allowed,
            chat_key,
            "approved" if allowed else "media_approval_required",
        )
    if chat_key == "internal":
        allowed = _has_department(user, "внутрен")
        return ChatAccessDecision(
            allowed,
            chat_key,
            "approved" if allowed else "wrong_department",
        )
    if chat_key == "external":
        allowed = _has_department(user, "внешн")
        return ChatAccessDecision(
            allowed,
            chat_key,
            "approved" if allowed else "wrong_department",
        )
    if chat_key == "leaders":
        allowed = user.role in PRIVILEGED_ROLES
        return ChatAccessDecision(
            allowed,
            chat_key,
            "approved" if allowed else "wrong_role",
        )
    return ChatAccessDecision(False, chat_key, "unknown_chat")


def access_message(reason: str) -> str:
    messages = {
        "not_registered": "Чтобы вступить в чат ЭРА, сначала пройдите регистрацию в боте.",
        "not_approved": "Регистрация получена. Дождитесь подтверждения администратора.",
        "blocked": "Доступ к чатам ЭРА временно закрыт. Если это ошибка, напишите администратору.",
        "archived": "Доступ к чатам ЭРА закрыт, потому что профиль находится в архиве.",
        "rejected": "Заявка в ЭРА не одобрена, поэтому доступ к закрытым чатам не открыт.",
        "wrong_department": "Этот чат доступен только участникам соответствующего направления ЭРА.",
        "wrong_role": "Этот чат доступен только лидерам и команде ЭРА.",
        "media_approval_required": "Media Chat доступен только участникам, которых одобрил руководитель Медиа.",
        "unknown_chat": "Этот чат не найден в настройках доступа ЭРА.",
    }
    return messages.get(reason, "Доступ к этому чату пока не открыт.")


async def remember_join_request(
    session: AsyncSession,
    *,
    chat_id: int,
    user_id: int,
    chat_key: str,
    reason: str,
) -> None:
    current = await session.scalar(
        select(PendingChatJoinRequest).where(
            PendingChatJoinRequest.chat_id == chat_id,
            PendingChatJoinRequest.user_id == user_id,
        )
    )
    if current:
        current.chat_key, current.status, current.reason = chat_key, "pending", reason
    else:
        session.add(
            PendingChatJoinRequest(
                chat_id=chat_id,
                user_id=user_id,
                chat_key=chat_key,
                status="pending",
                reason=reason,
            )
        )


async def close_join_request(
    session: AsyncSession,
    *,
    chat_id: int,
    user_id: int,
    status: str,
    reason: str,
) -> None:
    current = await session.scalar(
        select(PendingChatJoinRequest).where(
            PendingChatJoinRequest.chat_id == chat_id,
            PendingChatJoinRequest.user_id == user_id,
        )
    )
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


async def unrestrict_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=writable_permissions(),
        )
        return True
    except TelegramAPIError:
        logger.exception(
            "Could not restore write permissions chat=%s user=%s", chat_id, user_id
        )
        return False


async def remove_rejected_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Legacy helper kept for compatibility; chat sync no longer removes rejected users."""
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        return True
    except TelegramAPIError:
        logger.exception("Could not remove rejected member chat=%s user=%s", chat_id, user_id)
        return False


async def ensure_general_registration_pin(
    bot: Bot,
    chat_id: int,
    session_factory,
) -> bool:
    """Replace the old bot-owned pin with the current registration CTA once.

    A durable NotificationDelivery key prevents duplicate pinned posts after
    restarts. If the currently pinned message belongs to ERA Bot, edit it in
    place; otherwise send a new message and pin that one without deleting
    unrelated historical pins.
    """
    payload_hash = hashlib.sha256(
        GENERAL_REGISTRATION_PIN_TEXT.encode("utf-8")
    ).hexdigest()
    now = datetime.now().astimezone()

    async with session_factory() as session:
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.delivery_key == GENERAL_REGISTRATION_PIN_KEY
            )
        )
        if delivery and delivery.status == "sent":
            return True

        try:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🚀 Начать",
                            url=GENERAL_REGISTRATION_START_URL,
                        )
                    ]
                ]
            )
            me = await bot.get_me()
            chat = await bot.get_chat(chat_id)
            pinned = getattr(chat, "pinned_message", None)
            message_id: int | None = None

            if (
                pinned is not None
                and getattr(pinned, "from_user", None) is not None
                and pinned.from_user.id == me.id
            ):
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=pinned.message_id,
                        text=GENERAL_REGISTRATION_PIN_TEXT,
                        parse_mode="HTML",
                        reply_markup=markup,
                        disable_web_page_preview=True,
                    )
                    message_id = pinned.message_id
                except TelegramAPIError:
                    logger.exception(
                        "Could not edit existing general chat pin; creating a new pin"
                    )

            if message_id is None:
                message = await bot.send_message(
                    chat_id=chat_id,
                    text=GENERAL_REGISTRATION_PIN_TEXT,
                    parse_mode="HTML",
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )
                message_id = message.message_id

            await bot.pin_chat_message(
                chat_id=chat_id,
                message_id=message_id,
                disable_notification=True,
            )

            if delivery is None:
                delivery = NotificationDelivery(
                    delivery_key=GENERAL_REGISTRATION_PIN_KEY,
                    chat_id=chat_id,
                    notification_type="general_registration_pin",
                    status="sent",
                    attempt_count=1,
                    last_attempt_at=now,
                    sent_at=now,
                    error_code=None,
                    payload_hash=payload_hash,
                )
                session.add(delivery)
            else:
                delivery.chat_id = chat_id
                delivery.status = "sent"
                delivery.attempt_count += 1
                delivery.last_attempt_at = now
                delivery.sent_at = now
                delivery.error_code = None
                delivery.payload_hash = payload_hash

            await session.commit()
            logger.info(
                "General registration CTA pinned chat=%s message=%s",
                chat_id,
                message_id,
            )
            return True
        except TelegramAPIError as exc:
            logger.exception("Could not publish general registration pin chat=%s", chat_id)
            if delivery is None:
                delivery = NotificationDelivery(
                    delivery_key=GENERAL_REGISTRATION_PIN_KEY,
                    chat_id=chat_id,
                    notification_type="general_registration_pin",
                    status="failed",
                    attempt_count=1,
                    last_attempt_at=now,
                    sent_at=None,
                    error_code=exc.__class__.__name__[:96],
                    payload_hash=payload_hash,
                )
                session.add(delivery)
            else:
                delivery.status = "failed"
                delivery.attempt_count += 1
                delivery.last_attempt_at = now
                delivery.error_code = exc.__class__.__name__[:96]
                delivery.payload_hash = payload_hash
            await session.commit()
            return False


async def ensure_general_chat_writable(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> tuple[int, int]:
    """Keep the general chat writable for everyone.

    This recurring maintenance job changes Telegram permissions only. It must
    never publish, edit or pin messages in the public chat.
    """
    chat_id = getattr(settings, "general_chat_id", None)
    if not chat_id:
        return 0, 0

    fixed = failed = 0
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=writable_permissions(),
        )
        fixed += 1
    except TelegramAPIError:
        logger.exception("Could not set default writable permissions chat=%s", chat_id)
        failed += 1

    async with session_factory() as session:
        users = (await session.scalars(select(User))).all()

    for user in users:
        try:
            member = await bot.get_chat_member(
                chat_id=chat_id,
                user_id=user.telegram_id,
            )
            raw_status = getattr(member, "status", "")
            status = str(getattr(raw_status, "value", raw_status)).casefold()
            if status not in {"member", "administrator", "creator", "restricted"}:
                continue
            if await unrestrict_member(bot, chat_id, user.telegram_id):
                fixed += 1
            else:
                failed += 1
        except TelegramAPIError:
            continue

    return fixed, failed


async def notify_user(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except TelegramForbiddenError:
        return
    except TelegramAPIError:
        logger.exception("Could not notify user %s about chat access", user_id)


async def sync_user_chat_access(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    user: User,
) -> tuple[int, int]:
    fixed = failed = 0
    pending = (
        await session.scalars(
            select(PendingChatJoinRequest).where(
                PendingChatJoinRequest.user_id == user.telegram_id,
                PendingChatJoinRequest.status == "pending",
            )
        )
    ).all()
    for item in pending:
        decision = check_chat_access(user, item.chat_key)
        if not decision.allowed:
            item.reason = decision.reason
            if not decision.pending:
                if await decline_join_request(bot, item.chat_id, item.user_id):
                    item.status = "declined"
                    fixed += 1
                else:
                    failed += 1
            continue
        if await approve_join_request(bot, item.chat_id, item.user_id):
            item.status = "approved"
            item.reason = "approved"
            fixed += 1
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
        await audit(
            session,
            actor_id=user.id,
            action="chat_access.synced",
            entity_type="user",
            entity_id=user.id,
            new_value={
                "telegram_id": user.telegram_id,
                "fixed": fixed,
                "failed": failed,
            },
        )
    return fixed, failed
