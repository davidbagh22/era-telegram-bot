from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database.system_models import NotificationDelivery

logger = logging.getLogger(__name__)

GENERAL_CHAT_MENU_KEY = "general-chat-miniapp-menu-v1"
GENERAL_CHAT_MENU_TEXT = (
    "<b>ЭРА теперь в одном боте.</b>\n\n"
    "Мероприятия, личное портфолио, сертификаты, баллы за активность, "
    "возможности от партнёров и инструменты для развития — теперь всё в одном месте.\n\n"
    "Выбери нужный раздел ниже."
)

# Telegram Main Mini App deep links. tgWebAppStartParam is already handled by
# the frontend router: `events` opens EventsScreen and `home` opens My ERA.
EVENTS_MINIAPP_URL = "https://t.me/ERA_1bot?startapp=events"
MY_ERA_MINIAPP_URL = "https://t.me/ERA_1bot?startapp=home"


def _menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Мероприятия", url=EVENTS_MINIAPP_URL),
                InlineKeyboardButton(text="👤 Моя ЭРА", url=MY_ERA_MINIAPP_URL),
            ]
        ]
    )


async def ensure_general_chat_miniapp_menu(
    bot: Bot,
    chat_id: int | None,
    session_factory,
) -> bool:
    """Put two direct Mini App entry points on the bot-owned general-chat pin.

    The delivery key is durable so ordinary restarts do not create duplicate
    posts. If ERA Bot owns the current pin, it is edited in place; otherwise a
    new bot-owned message is created and pinned without deleting unrelated pins.
    """
    if not chat_id:
        return False

    payload_hash = hashlib.sha256(
        (GENERAL_CHAT_MENU_TEXT + EVENTS_MINIAPP_URL + MY_ERA_MINIAPP_URL).encode("utf-8")
    ).hexdigest()
    now = datetime.now().astimezone()

    async with session_factory() as session:
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.delivery_key == GENERAL_CHAT_MENU_KEY
            )
        )
        if delivery and delivery.status == "sent" and delivery.payload_hash == payload_hash:
            return True

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
                        text=GENERAL_CHAT_MENU_TEXT,
                        parse_mode="HTML",
                        reply_markup=_menu_markup(),
                        disable_web_page_preview=True,
                    )
                    message_id = pinned.message_id
                except TelegramAPIError:
                    logger.exception("Could not edit general chat pin with Mini App menu")

            if message_id is None:
                message = await bot.send_message(
                    chat_id=chat_id,
                    text=GENERAL_CHAT_MENU_TEXT,
                    parse_mode="HTML",
                    reply_markup=_menu_markup(),
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
                    delivery_key=GENERAL_CHAT_MENU_KEY,
                    chat_id=chat_id,
                    notification_type="general_chat_miniapp_menu",
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
            logger.info("General chat Mini App menu pinned chat=%s message=%s", chat_id, message_id)
            return True
        except TelegramAPIError as exc:
            logger.exception("Could not publish general chat Mini App menu chat=%s", chat_id)
            if delivery is None:
                delivery = NotificationDelivery(
                    delivery_key=GENERAL_CHAT_MENU_KEY,
                    chat_id=chat_id,
                    notification_type="general_chat_miniapp_menu",
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
