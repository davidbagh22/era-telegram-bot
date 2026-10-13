from __future__ import annotations

from aiogram import Bot
from aiogram.types import ChatPermissions

from app.config import Settings


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
    """Never lift a restriction whose moderation provenance is unknown."""
    return False


async def enforce_general_chat_writable(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> tuple[int, int]:
    """Legacy scheduler hook; chat permissions belong to moderators."""
    return 0, 0
