from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import select

from app.config import Settings
from app.services.general_topics_service import send_general_topic
from app.database.event_experience import EventExperience, EventReminderDelivery
from app.database.models import Event, EventRegistration, User
from app.services.bot_notification_service import PrimaryAction, send_bot_notification
from app.services.event_service import event_datetime
from app.utils.constants import EventStatus, RegistrationStatus
from app.utils.deep_links import miniapp_event_url


def _configured_thresholds(values) -> list[int]:
    """Ignore malformed legacy JSON values without aborting every reminder.

    Valid positive minute thresholds keep their previous ordering and
    de-duplication. Booleans are not minute values despite int(True) == 1.
    """
    if not isinstance(values, (list, tuple)):
        return []
    thresholds: set[int] = set()
    for value in values:
        # Do not truncate fractional floats or coerce arbitrary JSON objects:
        # those can unexpectedly activate real Telegram sends.
        if type(value) is int:
            minutes = value
        elif isinstance(value, str):
            candidate = value.strip()
            if not candidate or len(candidate) > 9 or not candidate.isascii() or not candidate.isdigit():
                continue
            minutes = int(candidate)
        else:
            continue
        # Reject nonsensical legacy values and anything outside a one-year
        # reminder horizon; the DB receipt key stores minutes as an integer.
        if 0 < minutes <= 525600:
            thresholds.add(minutes)
    return sorted(thresholds)


async def send_configured_event_reminders(bot: Bot, settings: Settings, session_factory) -> None:
    """Send the nearest configured reminder threshold exactly once per registration.

    The semantic delivery key is written before Telegram is called. The existing
    EventReminderDelivery remains the domain-level marker, so a crash after the
    Telegram send but before the domain commit completes the marker on restart
    without sending a second message.
    """
    now = datetime.now(ZoneInfo(settings.timezone))
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(EventRegistration, Event, EventExperience, User)
                .join(Event, Event.id == EventRegistration.event_id)
                .join(EventExperience, EventExperience.event_id == Event.id)
                .join(User, User.id == EventRegistration.user_id)
                .where(
                    Event.status.in_([
                        EventStatus.APPROVED,
                        EventStatus.PUBLISHED,
                        EventStatus.REGISTRATION_OPEN,
                    ]),
                    EventRegistration.status.in_([
                        RegistrationStatus.REGISTERED,
                        RegistrationStatus.WILL_COME,
                    ]),
                )
            )
        ).all()
        for registration, event, experience, user in rows:
            configured = _configured_thresholds(experience.reminders)
            if not configured:
                continue
            minutes_left = (event_datetime(event, settings.timezone) - now).total_seconds() / 60
            if minutes_left <= 0:
                continue
            eligible = [minutes for minutes in configured if minutes_left <= minutes]
            if not eligible:
                continue
            threshold = min(eligible)
            await send_general_topic(
                bot, settings, "announcements",
                f"⏰ Напоминаем о мероприятии\n\n{event.title}\n"
                f"📅 {event.event_date:%d.%m.%Y} · {event.event_time:%H:%M}\n📍 {event.location}",
                delivery_key=f"event:{event.id}:reminder:{threshold}:{event.event_date}:{event.event_time}",
            )
            already = await session.scalar(
                select(EventReminderDelivery.id).where(
                    EventReminderDelivery.registration_id == registration.id,
                    EventReminderDelivery.reminder_minutes == threshold,
                )
            )
            if already:
                continue
            if threshold >= 1440:
                lead = "Завтра встречаемся" if threshold <= 1500 else "Напоминаем о событии"
            elif threshold >= 60:
                lead = f"До события около {max(1, round(threshold / 60))} ч"
            else:
                lead = f"До события около {threshold} мин"
            url = miniapp_event_url(settings.effective_miniapp_url, event.id)
            sent = await send_bot_notification(
                bot,
                user.telegram_id,
                emoji="🔥",
                title=lead,
                body=(
                    f"{event.title}\n\n"
                    f"📅 {event.event_date:%d.%m.%Y} · {event.event_time:%H:%M}\n"
                    f"📍 {event.location}"
                ),
                footer="Если планы изменились — отмените участие, чтобы место смог занять другой участник.",
                action=(
                    PrimaryAction(label="Открыть мероприятие", web_app_url=url)
                    if url
                    else None
                ),
                settings=settings,
                delivery_key=f"event-custom-reminder:{registration.id}:{threshold}",
                notification_type="event_custom_reminder",
            )
            if not sent:
                continue
            session.add(
                EventReminderDelivery(
                    registration_id=registration.id,
                    reminder_minutes=threshold,
                    sent_at=now,
                )
            )
            registration.last_reminder_at = now
        await session.commit()
