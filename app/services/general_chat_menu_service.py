from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database.system_models import NotificationDelivery
from app.keyboards.faq import general_chat_navigation_keyboard
from app.services.chat_access_service import (
    GENERAL_REGISTRATION_PIN_TEXT,
    GENERAL_REGISTRATION_START_URL,
)

logger = logging.getLogger(__name__)

GENERAL_CHAT_NAV_KEY = "general-chat-persistent-nav-v1"
GENERAL_CHAT_NAV_TEXT = "Навигация ЭРА доступна внизу чата."


def _registration_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Начать",
                    url=GENERAL_REGISTRATION_START_URL,
                )
            ]
        ]
    )


async def _restore_registration_pin(bot: Bot, chat_id: int) -> bool:
    """Keep the pinned CTA exactly as the original registration message."""
    try:
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
                    reply_markup=_registration_markup(),
                    disable_web_page_preview=True,
                )
                message_id = pinned.message_id
            except TelegramAPIError:
                logger.exception("Could not restore existing registration pin")

        if message_id is None:
            message = await bot.send_message(
                chat_id=chat_id,
                text=GENERAL_REGISTRATION_PIN_TEXT,
                parse_mode="HTML",
                reply_markup=_registration_markup(),
                disable_web_page_preview=True,
            )
            message_id = message.message_id

        await bot.pin_chat_message(
            chat_id=chat_id,
            message_id=message_id,
            disable_notification=True,
        )
        return True
    except TelegramAPIError:
        logger.exception("Could not restore registration pin chat=%s", chat_id)
        return False


async def _ensure_persistent_navigation(
    bot: Bot,
    chat_id: int,
    session_factory,
) -> bool:
    """Publish the persistent reply keyboard once for every group member.

    Telegram does not support Web App buttons inside a group reply keyboard.
    These two text buttons are handled by app.handlers.chat: the trigger is
    deleted from the group and the corresponding Mini App action is sent to
    that participant in private.
    """
    payload_hash = hashlib.sha256(
        (GENERAL_CHAT_NAV_TEXT + "|📅 Мероприятия|👤 Моя ЭРА").encode("utf-8")
    ).hexdigest()
    now = datetime.now().astimezone()

    async with session_factory() as session:
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.delivery_key == GENERAL_CHAT_NAV_KEY
            )
        )
        if delivery and delivery.status == "sent" and delivery.payload_hash == payload_hash:
            return True

        try:
            message = await bot.send_message(
                chat_id=chat_id,
                text=GENERAL_CHAT_NAV_TEXT,
                reply_markup=general_chat_navigation_keyboard(),
                disable_notification=True,
            )
            if delivery is None:
                delivery = NotificationDelivery(
                    delivery_key=GENERAL_CHAT_NAV_KEY,
                    chat_id=chat_id,
                    notification_type="general_chat_persistent_nav",
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
                "Persistent general-chat navigation published chat=%s message=%s",
                chat_id,
                message.message_id,
            )
            return True
        except TelegramAPIError as exc:
            logger.exception("Could not publish persistent navigation chat=%s", chat_id)
            if delivery is None:
                delivery = NotificationDelivery(
                    delivery_key=GENERAL_CHAT_NAV_KEY,
                    chat_id=chat_id,
                    notification_type="general_chat_persistent_nav",
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


async def ensure_general_chat_miniapp_menu(
    bot: Bot,
    chat_id: int | None,
    session_factory,
) -> bool:
    """Restore the Start pin and keep two navigation buttons by the input field."""
    if not chat_id:
        return False
    pin_ok = await _restore_registration_pin(bot, chat_id)
    nav_ok = await _ensure_persistent_navigation(bot, chat_id, session_factory)
    return pin_ok and nav_ok
