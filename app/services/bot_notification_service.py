from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.config import Settings
from app.services.notification_service import safe_send, safe_send_once


@dataclass(frozen=True)
class PrimaryAction:
    label: str
    callback_data: str | None = None
    web_app_url: str | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        targets = [self.callback_data, self.web_app_url, self.url]
        if sum(value is not None for value in targets) != 1:
            raise ValueError("primary action must have exactly one target")


def action_markup(action: PrimaryAction | None) -> InlineKeyboardMarkup | None:
    if action is None:
        return None
    if action.callback_data is not None:
        button = InlineKeyboardButton(text=action.label, callback_data=action.callback_data)
    elif action.web_app_url is not None:
        button = InlineKeyboardButton(
            text=action.label,
            web_app=WebAppInfo(url=action.web_app_url),
        )
    else:
        button = InlineKeyboardButton(text=action.label, url=action.url)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


async def send_bot_notification(
    bot: Bot,
    chat_id: int,
    *,
    title: str,
    body: str,
    action: PrimaryAction | None = None,
    emoji: str | None = None,
    footer: str | None = None,
    settings: Settings | None = None,
    delivery_key: str | None = None,
    notification_type: str = "bot_notification",
) -> bool:
    """Send one consistent ERA notification with at most one primary action.

    Interactive, one-off notifications can keep the lightweight transport by
    omitting ``settings`` and ``delivery_key``. Every scheduled/repeatable flow
    must provide both; it then uses the central durable idempotency ledger.
    This keeps one notification service rather than creating a parallel engine.
    """
    if (settings is None) != (delivery_key is None):
        raise ValueError("settings and delivery_key must be provided together")

    heading = f"{emoji} {title}" if emoji else title
    parts = [heading.strip(), body.strip()]
    if footer:
        parts.append(footer.strip())
    text = "\n\n".join(part for part in parts if part)
    markup = action_markup(action)

    if settings is not None and delivery_key is not None:
        result = await safe_send_once(
            bot,
            settings,
            chat_id,
            text,
            delivery_key=delivery_key,
            notification_type=notification_type,
            reply_markup=markup,
        )
        return result.sent

    return await safe_send(
        bot,
        chat_id,
        text,
        reply_markup=markup,
    )
