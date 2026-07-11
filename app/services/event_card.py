from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message


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
    if available is not None:
        parts.append(f"Свободных мест: {available}")
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
    extra_text: str | None = None,
) -> None:
    text = format_event_text(event, header=header, available=available, extra_text=extra_text)
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
    extra_text: str | None = None,
) -> None:
    text = format_event_text(event, header=header, available=available, extra_text=extra_text)
    poster_file_id = getattr(event, "poster_file_id", None)
    if poster_file_id:
        try:
            if len(text) <= PHOTO_CAPTION_LIMIT:
                await bot.send_photo(chat_id, poster_file_id, caption=text, reply_markup=keyboard)
            else:
                await bot.send_photo(chat_id, poster_file_id, caption=event.title)
                await bot.send_message(chat_id, text, reply_markup=keyboard)
            return
        except Exception:
            pass
    await bot.send_message(chat_id, text, reply_markup=keyboard)
