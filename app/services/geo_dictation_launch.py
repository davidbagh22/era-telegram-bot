"""Publish the November 22 Geographic Dictation as an externally registered event.

This is a single owner-requested event, not an invitation to broadcast to all
private bot chats. Preserve the organizer's signup link and never replace it
with ERA's own registration form.
"""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
import logging

from sqlalchemy import or_, select, text

from app.database.event_experience import EventExperience
from app.database.models import Event, User
from app.services.authorization_service import can_manage_events
from app.services.event_publication_service import publish_event_announcement
from app.utils.constants import EventStatus

logger = logging.getLogger(__name__)

KEY = "geo-dictation-2026-russian-house"
TITLE = "Географический диктант — 2026"
EVENT_DATE = date(2026, 11, 22)
START_TIME = time(12, 0)
PLACE = "Русский дом"
SIGNUP_URL = "https://t.me/+quri_BnuHaxjZTVi"
DESCRIPTION = (
    "Приглашаем принять участие в ежегодной международной просветительской акции "
    "«Географический диктант — 2026»! 🌍\n\n"
    "Встречаемся в Русском доме 22 ноября в 12:00. "
    "Чтобы присоединиться, запишитесь по ссылке организаторов."
)


async def publish_geo_dictation(bot, settings, factory):
    now = datetime.now(ZoneInfo("Asia/Yerevan"))
    if (settings.dev_auth_enabled or settings.general_chat_id != -1002973371133
            or not date(2026, 11, 20) <= now.date() <= EVENT_DATE
            or (now.date() == EVENT_DATE and now.time() >= START_TIME)):
        return

    if (await bot.get_me()).username.lower() != "era_1bot":
        return

    async with factory() as session:
        # Serialize startup/recovery across old/new Render instances.
        async with session.bind.connect() as conn:
            acquired = await conn.scalar(text("SELECT pg_try_advisory_lock(202611221200)"))
            if not acquired:
                return
            try:
                await _ensure_event_and_publish(bot, settings, session)
            finally:
                await conn.execute(text("SELECT pg_advisory_unlock(202611221200)"))


async def _ensure_event_and_publish(bot, settings, session):
    matches = list(await session.scalars(select(Event).where(
        Event.event_date == EVENT_DATE,
        or_(Event.title == TITLE, Event.additional_info == KEY),
    )))
    if len(matches) > 1 or (matches and matches[0].additional_info != KEY):
        logger.warning("Geographic Dictation already exists without matching marker; manual reconciliation required")
        return

    if matches:
        event = matches[0]
        exp = await session.get(EventExperience, event.id)
    else:
        chair = (await session.get(User, settings.era_chair_user_id)
                 if settings.era_chair_user_id else None)
        if chair is None:
            chair = await session.scalar(select(User).where(
                or_(User.telegram_id.in_(settings.admin_ids), User.role == "admin"),
                User.is_blocked.is_(False), User.is_archived.is_(False),
            ))
        if chair is None or not can_manage_events(chair, settings, chair.telegram_id):
            logger.warning("Geographic Dictation needs an authorized creator")
            return
        event = Event(
            title=TITLE, description=DESCRIPTION, event_date=EVENT_DATE,
            event_time=START_TIME, location=PLACE, format="Офлайн",
            status=EventStatus.REGISTRATION_OPEN, points_for_visit=0,
            created_by=chair.id, approved_by=chair.id, additional_info=KEY,
        )
        session.add(event)
        await session.flush()
        exp = EventExperience(
            event_id=event.id, is_complete=True, creation_mode="quick",
            wizard_step=10, short_description=DESCRIPTION, full_description=DESCRIPTION,
            registration_required=False, contact=SIGNUP_URL,
            issue_certificate=False, broadcast_enabled=False,
            broadcast_targets=["project_topic", "general"],
            announcement_status="not_requested",
        )
        session.add(exp)
        await session.commit()

    if exp is None or event.status != EventStatus.REGISTRATION_OPEN:
        logger.warning("Geographic Dictation exists but is not publishable")
        return
    if exp.announcement_status == "sent":
        return
    if exp.announcement_status == "needs_attention":
        logger.warning("Geographic Dictation publication uncertain; inspect Telegram receipts")
        return
    delivered = await publish_event_announcement(bot, settings, session, event, exp)
    if delivered:
        exp.announcement_status = "sent"
        logger.info("Geographic Dictation published event_id=%s topic=%s", event.id, exp.chat_url)
    await session.commit()
