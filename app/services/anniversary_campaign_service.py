"""Owner-authorized #669 campaign. Disabled until the release is verified.

Uses the existing Event, AppSetting and notification ledger; never creates users,
memberships or a second registration list. All destinations are frozen at prepare.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import or_, select, text

from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, User
from app.database.system_models import NotificationDelivery
from app.services.general_topics_service import ensure_topic
from app.services.notification_service import safe_send_once
from app.utils.constants import EventStatus

logger = logging.getLogger(__name__)
KEY = "anniversary:2026:campaign"
MARKER = "[ERA_GUEST_RSVP:anniversary2026]"
URL = "https://t.me/ERA_1bot?start=anniversary2026"
TZ = ZoneInfo("Asia/Yerevan")
TITLE = "Первая годовщина ЭРА — 1 ГОД"
DESCRIPTION = "ЭРА — 1 ГОД! Приглашаем разделить с нами первую годовщину объединения. Вспомним достижения, поблагодарим тех, кто был рядом, и вместе откроем новую главу истории ЭРА. Ждём вас 12 декабря!"
LOCATION = "Кинозал Дома Москвы в Ереване, ул. Аргишти, 7"
ORGANIZER = "Объединение лидеров и культурных инициатив «ЭРА»"
POSTER_SHA = "6bc159a980bad0ec7cf27d23957add7a75dd42a4c22b37c948735719bc7d88c0"
POSTER = Path(__file__).resolve().parents[1] / "assets" / "anniversary2026.png"
DATES = tuple(datetime(2026, month, day, 18, tzinfo=TZ).isoformat()
              for month, day in ((11, 14), (11, 21), (11, 28), (12, 5), (12, 8), (12, 9), (12, 10), (12, 11)))
STOP = datetime(2026, 12, 12, 18, tzinfo=TZ)
COPY = f"{TITLE}\n\n{DESCRIPTION}\n\n12 декабря 2026\nСбор гостей — 17:30 · Начало — 18:00 (Ереван)\n{LOCATION}\n\nОрганизатор: {ORGANIZER}"


def is_anniversary(event) -> bool:
    return MARKER in (getattr(event, "additional_info", None) or "").splitlines()


def keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Зарегистрироваться", url=URL)
    ]])


async def prepare_campaign(bot, settings, factory):
    poster = POSTER.read_bytes()
    if hashlib.sha256(poster).hexdigest() != POSTER_SHA:
        raise ValueError("anniversary_original_poster_mismatch")
    # Read-only Telegram resolution; do not create a topic or fall back to main.
    me = await bot.get_me()
    if (me.username or "").lower() != "era_1bot":
        raise ValueError("anniversary_wrong_bot")
    channel = await bot.get_chat(settings.era_channel_id or settings.era_channel_username)
    if (channel.username or "").lower() != "era_leaders1":
        raise ValueError("anniversary_wrong_channel")
    thread = await ensure_topic(bot, settings, "announcements", session_factory=factory, create_if_missing=False)
    if not settings.general_chat_id or not thread:
        raise ValueError("anniversary_existing_topic_required")
    async with factory() as session:
        if session.bind.dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 66920261212})
        existing = await session.scalar(select(AppSetting).where(AppSetting.key == KEY))
        if existing is not None:
            return existing.value
        candidates = list((await session.scalars(select(Event).where(or_(
            Event.additional_info.contains(MARKER),
            (Event.event_date == date(2026, 12, 12)) & or_(
                Event.title.ilike("%год%"), Event.title.ilike("%anniversary%")
            ),
        )))).all())
        if candidates:
            # Never silently adopt or overwrite an existing event/publication.
            raise ValueError("anniversary_existing_event_requires_reconciliation:" + ",".join(str(e.id) for e in candidates))
        creator = await session.scalar(select(User).where(
            User.telegram_id.in_(settings.admin_ids), User.is_blocked.is_(False), User.is_archived.is_(False)
        ).order_by(User.id).limit(1))
        if creator is None:
            raise ValueError("anniversary_existing_admin_required")
        event = Event(title=TITLE, description=DESCRIPTION, event_date=date(2026, 12, 12),
                      event_time=time(18), location=LOCATION, format="Очно", access_type="all",
                      points_for_visit=0, selfie_required=False, created_by=creator.id, approved_by=creator.id,
                      status=EventStatus.REGISTRATION_OPEN,
                      additional_info=f"Сбор гостей — 17:30. Начало — 18:00 (Asia/Yerevan).\n{MARKER}")
        session.add(event)
        await session.flush()
        session.add(EventExperience(event_id=event.id, short_description=DESCRIPTION, full_description=DESCRIPTION,
            organizer=ORGANIZER, address=LOCATION, registration_required=True,
            registration_close_at=datetime(2026, 12, 12, 17, 30, tzinfo=TZ),
            registration_audience="anniversary2026", reminders=[], broadcast_targets=[], broadcast_enabled=False,
            is_complete=True, poster_bytes=poster, poster_content_type="image/png", announcement_status="not_requested"))
        targets = [{"name": "channel", "chat_id": channel.id, "thread_id": None},
                   {"name": "announcements", "chat_id": settings.general_chat_id, "thread_id": thread}]
        value = {"event_id": event.id, "poster_sha256": POSTER_SHA, "registration_url": URL,
                 "targets": targets, "dates": list(DATES), "copy": COPY,
                 "prepared_at": datetime.now(TZ).isoformat(), "deliveries": []}
        for target in targets:
            for slot in ("initial", *DATES):
                value["deliveries"].append({"key": f"{KEY}:{target['name']}:{slot}",
                    "due_at": value["prepared_at"] if slot == "initial" else slot,
                    "slot": slot, **target})
        session.add(AppSetting(key=KEY, value=value))
        await session.commit()
        return value


async def campaign_snapshot(factory):
    async with factory() as session:
        row = await session.scalar(select(AppSetting).where(AppSetting.key == KEY))
        if row is None:
            return {"prepared": False}
        value = row.value
        event = await session.get(Event, value["event_id"])
        exp = await session.get(EventExperience, value["event_id"])
        from app.services.event_service import published_events
        from app.services.activity_service import list_events
        from app.api.v1.events import _to_event_out
        creator = await session.get(User, event.created_by)
        bot_visible = event.id in [e.id for e in await published_events(session)]
        miniapp_visible = event.id in [e.id for e, _ in await list_events(session, creator, "all")]
        card = await _to_event_out(session, event, None)
        receipts = list((await session.scalars(select(NotificationDelivery).where(
            NotificationDelivery.delivery_key.in_([d["key"] for d in value["deliveries"]])
        ))).all())
        return {"prepared": True, "event_id": event.id, "status": event.status,
                "bot_visible": bot_visible, "miniapp_visible": miniapp_visible, "registration_url": card.registration_url,
                "guest_registration": is_anniversary(event), "dates": value["dates"], "targets": value["targets"],
                "poster_sha256": hashlib.sha256(exp.poster_bytes).hexdigest(),
                "deliveries_saved": len(value["deliveries"]),
                "receipts": [{"key": r.delivery_key, "status": r.status, "message_id": r.message_id,
                              "chat_id": r.chat_id} for r in receipts]}


async def run_campaign(bot, settings, factory, *, now=None):
    mode = getattr(settings, "anniversary_2026_campaign", "off")
    if mode not in {"prepare", "publish"}:
        return
    now = now or datetime.now(TZ)
    try:
        if now >= STOP:
            return
        value = await prepare_campaign(bot, settings, factory)
        if mode == "publish":
            async with factory() as session:
                event = await session.get(Event, value["event_id"])
                exp = await session.get(EventExperience, event.id)
                if event.status not in {EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN} or not is_anniversary(event):
                    raise ValueError("anniversary_event_not_public")
                poster = exp.poster_bytes
            if hashlib.sha256(poster).hexdigest() != value["poster_sha256"]:
                raise ValueError("anniversary_saved_poster_mismatch")
            for delivery in value["deliveries"]:
                if datetime.fromisoformat(delivery["due_at"]) > now:
                    continue
                await safe_send_once(bot, settings, delivery["chat_id"], value["copy"],
                    delivery_key=delivery["key"], notification_type="anniversary2026",
                    reply_markup=keyboard(), parse_mode=None, max_attempts=1,
                    message_thread_id=delivery["thread_id"], photo=BufferedInputFile(poster, filename="IMG_3322.PNG"))
        logger.info("ANNIVERSARY_669 %s", json.dumps(await campaign_snapshot(factory), ensure_ascii=False))
    except Exception:
        logger.exception("ANNIVERSARY_669 blocked")
