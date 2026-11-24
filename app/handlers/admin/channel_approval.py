"""Exact-day ERA channel publication approval (E09). Fail closed by default."""
from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting, User
from app.services.authorization_service import is_full_admin
from app.services.daily_public_content_service import (
    MOSCOW,
    _channel_target,
    _publication_digest,
    approve_channel_publication,
    text_for_day,
)
from app.utils import texts

router = Router(name="channel_approval")


def _pending_key(user_id: int) -> str:
    return f"era_daily_channel_approval_pending:{user_id}"


def _preview(text: str) -> str:
    body = text.strip()
    if len(body) > 700:
        return body[:700] + "…"
    return body


async def _store_pending(
    session: AsyncSession, *, user_id: int, day: str, target: str, digest: str
) -> None:
    key = _pending_key(user_id)
    payload = {"day": day, "target": target, "digest": digest}
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
    if row is None:
        session.add(AppSetting(key=key, value=payload, updated_by=user_id))
    else:
        row.value = payload
        row.updated_by = user_id
    await session.flush()


async def _load_pending(session: AsyncSession, user_id: int) -> dict | None:
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == _pending_key(user_id))
    )
    if row is None or not isinstance(row.value, dict):
        return None
    day, target, digest = row.value.get("day"), row.value.get("target"), row.value.get("digest")
    if (
        isinstance(day, str)
        and isinstance(target, str)
        and isinstance(digest, str)
        and len(digest) == 64
    ):
        return {"day": day, "target": target, "digest": digest}
    return None


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
    digest = _publication_digest(content)
    await _store_pending(
        session,
        user_id=user.id,
        day=day,
        target=str(target),
        digest=digest,
    )
    await session.commit()
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Согласовать этот текст на сегодня",
                    callback_data=f"admin:channel_approve:{day}:{digest[:16]}",
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


@router.callback_query(F.data.regexp(r"^admin:channel_approve:\d{4}-\d{2}-\d{2}:[0-9a-f]{16}$"))
async def approve_channel_post_confirm(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not is_full_admin(user, settings, call.from_user.id):
        await call.answer(texts.NO_ACCESS, show_alert=True)
        return
    _, _, day, digest_prefix = call.data.split(":", 3)
    today = datetime.now(MOSCOW).date().isoformat()
    if day != today:
        await call.answer("Можно согласовать только сегодняшний текст.", show_alert=True)
        return
    pending = await _load_pending(session, user.id)
    if (
        pending is None
        or pending["day"] != day
        or not pending["digest"].startswith(digest_prefix)
    ):
        await call.answer(
            "Превью устарело. Снова выполните /approve_channel_post.",
            show_alert=True,
        )
        return
    # Reject if the live bank/channel no longer matches what was previewed.
    target = _channel_target(settings)
    content = text_for_day(day, "channel_post")
    if target is None or str(target) != pending["target"]:
        await call.answer("Канал изменился. Откройте превью заново.", show_alert=True)
        return
    if _publication_digest(content) != pending["digest"]:
        await call.answer("Текст изменился. Откройте превью заново.", show_alert=True)
        return
    digest, already = await approve_channel_publication(
        session,
        day=pending["day"],
        target=pending["target"],
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
        f"Канал: {pending['target']}\nSHA-256: {digest[:16]}…\n"
        "Планировщик отправит её только в согласованное окно, без повторной отправки."
    )
