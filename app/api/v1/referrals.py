from __future__ import annotations

from html import escape

from aiogram import Bot
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, LinkPreviewOptions
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.models import User
from app.services.referral_service import (
    ACTIVE_REFERRAL_POINTS,
    FIRST_EVENT_REFERRAL_POINTS,
    REFERRAL_MONTHLY_CAP,
    REFERRAL_PER_INVITEE_CAP,
    REGISTRATION_REFERRAL_POINTS,
    get_referral_summary,
)

router = APIRouter(prefix="/referrals", tags=["referrals"])
OFFICIAL_GENERAL_CHAT_URL = "https://t.me/+Q6MzTrnR21dmZjgy"


def _rich_referral_text(*, code: str, invite_url: str, general_chat_url: str) -> str:
    bot_link = escape(invite_url or "https://t.me/ERA_1bot", quote=True)
    chat_link = escape(general_chat_url or OFFICIAL_GENERAL_CHAT_URL, quote=True)
    return (
        "🔥 <b>Тебя пригласили в ЭРА.</b>\n\n"
        "ЭРА — среда, где участие превращается в реальные проекты, роли, связи и возможности.\n\n"
        "Здесь не нужно ждать, пока тебя заметят. Можно включиться, взять ответственность и расти через дело.\n\n"
        f'<a href="{bot_link}">Войти в ЭРА</a>\n'
        f"Код приглашения: <code>{escape(code)}</code>\n\n"
        f'После регистрации — <a href="{chat_link}">общий чат ЭРА</a>. '
        "Там команда, проекты и всё движение сообщества.\n\n"
        "<b>Вход открыт. Остаются те, кто действительно включается.</b>"
    )


@router.get("/me")
async def my_referral_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    summary = await get_referral_summary(session, user=user, settings=settings)
    await session.commit()
    return {
        "code": summary.code,
        "invite_url": summary.invite_url,
        "share_text": summary.share_text,
        "registration_points_each": REGISTRATION_REFERRAL_POINTS,
        "first_event_points_each": FIRST_EVENT_REFERRAL_POINTS,
        "active_points_each": ACTIVE_REFERRAL_POINTS,
        "per_invitee_cap": REFERRAL_PER_INVITEE_CAP,
        "monthly_cap": REFERRAL_MONTHLY_CAP,
        "invited_count": summary.invited_count,
        "registered_count": summary.registered_count,
        "first_event_count": summary.first_event_count,
        "active_count": summary.active_count,
        "earned_points": summary.earned_points,
        "monthly_earned_points": summary.monthly_earned_points,
    }


@router.post("/share-message")
async def prepare_referral_share_message(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bot: Bot | None = Depends(get_bot),
) -> dict[str, str]:
    if bot is None:
        raise HTTPException(status_code=503, detail="telegram_share_unavailable")

    summary = await get_referral_summary(session, user=user, settings=settings)
    general_chat_url = (settings.general_chat_url or "").strip() or OFFICIAL_GENERAL_CHAT_URL
    result = InlineQueryResultArticle(
        id=f"era-ref-{summary.code}",
        title="Приглашение в ЭРА",
        description="Личная ссылка и код приглашения",
        input_message_content=InputTextMessageContent(
            message_text=_rich_referral_text(
                code=summary.code,
                invite_url=summary.invite_url,
                general_chat_url=general_chat_url,
            ),
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        ),
    )
    try:
        prepared = await bot.save_prepared_inline_message(
            user_id=user.telegram_id,
            result=result,
            allow_user_chats=True,
            allow_bot_chats=False,
            allow_group_chats=True,
            allow_channel_chats=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="telegram_share_prepare_failed") from exc
    return {"id": prepared.id}
