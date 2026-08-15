from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select

from app.config import Settings
from app.database.event_experience import EventExperience, EventReminderDelivery
from app.database.models import Event, EventRegistration, User
from app.services.event_service import event_datetime
from app.services.notification_service import safe_send
from app.utils.constants import EventStatus, RegistrationStatus
from app.utils.deep_links import miniapp_event_url


async def send_configured_event_reminders(bot: Bot, settings: Settings, session_factory) -> None:
    """Send the nearest configured reminder threshold exactly once per registration."""
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
            configured = sorted({int(value) for value in (experience.reminders or []) if int(value) > 0})
            if not configured:
                continue
            minutes_left = (event_datetime(event, settings.timezone) - now).total_seconds() / 60
            if minutes_left <= 0:
                continue
            eligible = [minutes for minutes in configured if minutes_left <= minutes]
            if not eligible:
                continue
            threshold = min(eligible)
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
            markup = (
                InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="Открыть мероприятие", web_app=WebAppInfo(url=url))]]
                )
                if url
                else None
            )
            sent = await safe_send(
                bot,
                user.telegram_id,
                f"🔥 {lead}\n\n{event.title}\n\n"
                f"📅 {event.event_date:%d.%m.%Y} · {event.event_time:%H:%M}\n"
                f"📍 {event.location}\n\n"
                "Если планы изменились — отмените участие, чтобы место смог занять другой участник.",
                reply_markup=markup,
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
