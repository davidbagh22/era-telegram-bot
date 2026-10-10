from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatPermissions
from sqlalchemy import select

from app.config import Settings
from app.database.models import User

logger = logging.getLogger(__name__)


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


async def restore_general_chat_member(
    bot: Bot,
    settings: Settings,
    telegram_id: int,
) -> bool:
    """Do not lift restrictions that may have been set by moderators.

    Telegram does not expose reliable provenance for member restrictions.
    Legacy repair therefore requires an explicit administrator decision.
    """
    return False


async def enforce_general_chat_writable(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> tuple[int, int]:
    """Compatibility hook; never rewrite chat permissions automatically."""
    return 0, 0
