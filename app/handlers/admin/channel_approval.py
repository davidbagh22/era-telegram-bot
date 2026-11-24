"""Exact-day ERA channel publication approval (E09). Fail closed by default."""
from __future__ import annotations

import hashlib
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.services.authorization_service import is_full_admin
from app.services.daily_public_content_service import (
    MOSCOW,
    _channel_target,
    approve_channel_publication,
    text_for_day,
)
from app.utils import texts

router = Router(name="channel_approval")


def _preview(text: str) -> str:
    body = text.strip()
    if len(body) > 700:
        return body[:700] + "…"
    return body


@router.message(Command("approve_channel_post"))
async def approve_channel_post_preview(
    message: Message, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not is_full_admin(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return
    target = _channel_target(settings)
    if target is None:
        await message.answer("Канал ЭРА не настроен — согласовать публикацию нельзя.")
        return
    day = datetime.now(MOSCOW).date().isoformat()
    content = text_for_day(day, "channel_post")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Согласовать этот текст на сегодня",
                    callback_data=f"admin:channel_approve:{day}",
                )
            ]
        ]
    )
    await message.answer(
        "📢 Согласование публикации в канал ЭРА\n\n"
        f"День (Москва): {day}\n"
        f"Канал: {target}\n"
        f"SHA-256: {digest[:16]}…\n\n"
        f"{_preview(content)}\n\n"
        "Согласование действует только для этой точной даты, канала и текста.",
        reply_markup=markup,
    )


@router.callback_query(F.data.regexp(r"^admin:channel_approve:\d{4}-\d{2}-\d{2}$"))
async def approve_channel_post_confirm(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not is_full_admin(user, settings, call.from_user.id):
        await call.answer(texts.NO_ACCESS, show_alert=True)
        return
    day = call.data.rsplit(":", 1)[-1]
    today = datetime.now(MOSCOW).date().isoformat()
    if day != today:
        await call.answer("Можно согласовать только сегодняшний текст.", show_alert=True)
        return
    target = _channel_target(settings)
    if target is None:
        await call.answer("Канал не настроен.", show_alert=True)
        return
    content = text_for_day(day, "channel_post")
    digest, already = await approve_channel_publication(
        session,
        day=day,
        target=str(target),
        text=content,
        actor_id=user.id if user else None,
    )
    await session.commit()
    await call.answer()
    if already:
        await call.message.answer(
            f"Публикация на {day} уже была согласована (SHA {digest[:16]}…)."
        )
        return
    await call.message.answer(
        f"✅ Публикация на {day} согласована.\n"
        f"Канал: {target}\nSHA-256: {digest[:16]}…\n"
        "Планировщик отправит её только в согласованное окно, без повторной отправки."
    )
