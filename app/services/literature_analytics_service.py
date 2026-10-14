"""Private daily digest of literature participation for configured administrators."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.book_club_service import literature_stats, format_literature_stats
from app.services.notification_service import safe_send_once


async def send_literature_admin_digest(bot, settings, session_factory):
    today = datetime.now(ZoneInfo("Asia/Yerevan")).date()
    if today.isoformat() < "2026-10-10" or today.isoformat() > "2026-11-26":
        return
    async with session_factory() as session:
        stats = await literature_stats(session)
    message = format_literature_stats(stats)
    for admin_id in settings.admin_ids:
        await safe_send_once(
            bot, settings, admin_id, message,
            delivery_key=f"literature-admin-digest:{today.isoformat()}:{admin_id}",
            notification_type="literature_admin_digest", parse_mode="HTML",
        )
