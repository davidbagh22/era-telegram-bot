from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message

from app.services.notification_service import safe_send, safe_send_photo


PHOTO_CAPTION_LIMIT = 1000


def _clean_additional_info(value: str | None) -> str:
    if not value:
        return ""
    lines = []
    for line in value.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[ERA_") and stripped.endswith("]"):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def format_event_text(
    event: Any,
    *,
    header: str | None = None,
    available: str | None = None,
    registered: int | None = None,
    extra_text: str | None = None,
) -> str:
    parts = []
    if header:
        parts.append(header)
    parts.append(str(event.title))
    parts.append(
        "\n".join(
            [
                f"Дата: {event.event_date:%d.%m.%Y}",
                f"Время: {event.event_time:%H:%M}",
                f"Место: {event.location}",
                f"Формат: {event.format}",
            ]
        )
    )
    if getattr(event, "description", None):
        parts.append(str(event.description))
    additional = _clean_additional_info(getattr(event, "additional_info", None))
    if additional:
        parts.append(additional)
    registration_lines = []
    if registered is not None:
        registration_lines.append(f"Зарегистрировано: {registered}")
    if available is not None:
        registration_lines.append(f"Свободных мест: {available}")
    if registration_lines:
        parts.append("\n".join(registration_lines))
    points = getattr(event, "points_for_visit", None)
    if points is not None:
        parts.append(f"Баллы за участие: {points}")
    if extra_text:
        parts.append(extra_text)
    return "\n\n".join(parts)


async def send_event_card(
    target: Message,
    event: Any,
    *,
    keyboard: InlineKeyboardMarkup | None = None,
    header: str | None = None,
    available: str | None = None,
    registered: int | None = None,
    extra_text: str | None = None,
) -> None:
    text = format_event_text(
        event,
        header=header,
        available=available,
        registered=registered,
        extra_text=extra_text,
    )
    poster_file_id = getattr(event, "poster_file_id", None)
    if poster_file_id:
        try:
            if len(text) <= PHOTO_CAPTION_LIMIT:
                await target.answer_photo(poster_file_id, caption=text, reply_markup=keyboard)
            else:
                await target.answer_photo(poster_file_id, caption=event.title)
                await target.answer(text, reply_markup=keyboard)
            return
        except Exception:
            pass
    await target.answer(text, reply_markup=keyboard)


async def send_event_card_to_chat(
    bot: Bot,
    chat_id: int,
    event: Any,
    *,
    keyboard: InlineKeyboardMarkup | None = None,
    header: str | None = None,
    available: str | None = None,
    registered: int | None = None,
    extra_text: str | None = None,
) -> None:
    text = format_event_text(
        event,
        header=header,
        available=available,
        registered=registered,
        extra_text=extra_text,
    )
    poster_file_id = getattr(event, "poster_file_id", None)
    if poster_file_id:
        if len(text) <= PHOTO_CAPTION_LIMIT:
            if await safe_send_photo(bot, chat_id, poster_file_id, caption=text, reply_markup=keyboard):
                return
        else:
            if await safe_send_photo(bot, chat_id, poster_file_id, caption=event.title):
                await safe_send(bot, chat_id, text, reply_markup=keyboard)
                return
    await safe_send(bot, chat_id, text, reply_markup=keyboard)
