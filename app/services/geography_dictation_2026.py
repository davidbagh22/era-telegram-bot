"""Create and publish the chair-approved partner event exactly once in ERA.

The external Telegram invitation is the organizer's registration path. ERA
must not promise/record attendance, certificates or points for this event.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, text

from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, User
from app.services.authorization_service import can_manage_events
from app.services.event_publication_service import publish_event_announcement
from app.utils.constants import EventStatus

log = logging.getLogger(__name__)

MARKER = "geography-dictation-2026"
TITLE = "Географический диктант — 2026"
REGISTRATION_URL = "https://t.me/+quri_BnuHaxjZTVi"
DATE = date(2026, 11, 22)
WHEN = time(12, 0)
LOCATION = "Русский дом, Ереван"
DESCRIPTION = (
    "Приглашаем принять участие в ежегодной международной просветительской "
    "акции «Географический диктант — 2026»! 🌍\n\n"
    "Проверим свои географические знания и проведём время с пользой. "
    "Чтобы принять участие, перейдите в регистрационный чат организаторов."
)


async def publish_geography_dictation(bot, settings, factory) -> None:
    """Recover on restart without creating duplicate events, topics or posts."""
    now = datetime.now(ZoneInfo("Asia/Yerevan"))
    if (settings.dev_auth_enabled or settings.general_chat_id != -1002973371133
            or not datetime(2026, 11, 20, tzinfo=ZoneInfo("Asia/Yerevan")) <= now
            < datetime(2026, 11, 22, 12, tzinfo=ZoneInfo("Asia/Yerevan"))):
        return
    if (await bot.get_me()).username.lower() != "era_1bot":
        return
    async with factory() as session:
        async with session.bind.connect() as conn:
            if not await conn.scalar(text("SELECT pg_try_advisory_lock(2026112212001)")):
                return
            try:
                await _publish_locked(bot, settings, session)
            finally:
                await conn.execute(text("SELECT pg_advisory_unlock(2026112212001)"))


async def _publish_locked(bot, settings, session) -> None:
    receipt = await session.scalar(select(AppSetting).where(AppSetting.key == MARKER))
    if receipt and isinstance(receipt.value, dict) and receipt.value.get("complete"):
        return

    existing = list(await session.scalars(select(Event).where(
        Event.event_date == DATE,
        or_(Event.additional_info == MARKER, Event.title == TITLE),
    )))
    if len(existing) > 1 or (existing and existing[0].additional_info != MARKER):
        log.warning("Geography Dictation already exists without the approved marker; manual reconciliation required")
        return

    if existing:
        event = existing[0]
        experience = await session.get(EventExperience, event.id)
    else:
        chair = await session.get(User, settings.era_chair_user_id) if settings.era_chair_user_id else None
        if chair is None:
            chair = await session.scalar(select(User).where(
                or_(User.telegram_id.in_(settings.admin_ids), User.role == "admin"),
                User.is_blocked.is_(False), User.is_archived.is_(False),
            ).order_by(User.id))
        if not chair or not can_manage_events(chair, settings, chair.telegram_id):
            log.warning("Geography Dictation: ERA chair role not available")
            return
        event = Event(
            title=TITLE, description=DESCRIPTION, event_date=DATE,
            event_time=WHEN, location=LOCATION, format="Офлайн",
            points_for_visit=0, status=EventStatus.PUBLISHED,
            created_by=chair.id, approved_by=chair.id, additional_info=MARKER,
        )
        session.add(event)
        await session.flush()
        experience = EventExperience(
            event_id=event.id, is_complete=True, creation_mode="quick", wizard_step=10,
            full_description=DESCRIPTION, short_description="Ежегодная международная просветительская акция",
            category="Просветительская акция", issue_certificate=False,
            registration_required=False, registration_url=REGISTRATION_URL,
            reminders=[], broadcast_enabled=False, broadcast_targets=["project_topic", "general"],
            announcement_status="pending",
        )
        session.add(experience)
        await session.commit()
        log.info("Geography Dictation created event_id=%s external_signup=True", event.id)

    if not experience or event.status != EventStatus.PUBLISHED:
        log.warning("Geography Dictation: existing event needs manual reconciliation")
        return
    if experience.announcement_status == "needs_attention":
        log.warning("Geography Dictation publication needs delivery reconciliation event_id=%s", event.id)
        return
    if experience.announcement_status != "sent":
        if not await publish_event_announcement(bot, settings, session, event, experience):
            await session.commit()
            log.warning("Geography Dictation publication pending event_id=%s", event.id)
            return
        experience.announcement_status = "sent"
        await session.commit()

    if receipt is None:
        session.add(AppSetting(key=MARKER, value={
            "complete": True, "event_id": event.id, "topic": experience.chat_url,
            "external_registration": True,
        }))
    else:
        receipt.value = {"complete": True, "event_id": event.id, "topic": experience.chat_url, "external_registration": True}
    await session.commit()
    log.info("Geography Dictation published event_id=%s topic=%s", event.id, experience.chat_url)
