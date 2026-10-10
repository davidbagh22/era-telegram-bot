"""General-chat permissions are managed by human Telegram moderators.

Older ERA builds attempted to grant write permissions to every restricted
member on a timer or private interaction. Telegram does not expose whether
a restriction came from ERA or a human moderator, so automated restoration
could silently undo a moderation decision. Keep these public call points
for existing handlers/jobs, but never mutate permissions automatically.
"""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import ChatPermissions

from app.config import Settings


def writable_permissions() -> ChatPermissions:
    """Permission template for a future explicit, audited moderator action."""
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
    """Do not remove individual restrictions without verified provenance.

    A `restricted` status is not proof that ERA applied the restriction.
    Restoration requires an explicit, authenticated moderator workflow.
    """
    return False


async def enforce_general_chat_writable(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> tuple[int, int]:
    """Deprecated scheduled job: intentionally perform no Telegram writes.

    This preserves the scheduler's return contract without calling
    set_chat_permissions or restrict_chat_member, even if the bot has
    administrator rights. Telegram chat defaults are moderator-owned.
    """
    return 0, 0
