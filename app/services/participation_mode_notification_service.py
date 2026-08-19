from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import select

from app.config import Settings
from app.database.models import User
from app.database.participation_models import ParticipationLifecycle
from app.database.participation_notification_models import ParticipationModeDelivery
from app.services.participation_lifecycle_service import MODE_OBSERVER, MODE_PAUSED
from app.utils.constants import ApplicationStatus

PAUSE_REMINDER_DAYS = 3
OBSERVER_CHECKIN_DAYS = 90
QUIET_START_HOUR = 22
QUIET_END_HOUR = 9


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _inside_quiet_hours(settings: Settings, now: datetime) -> bool:
    local = now.astimezone(ZoneInfo(settings.timezone))
    return local.hour >= QUIET_START_HOUR or local.hour < QUIET_END_HOUR


async def _delivery(
    session,
    *,
    user_id: int,
    kind: str,
    key: str,
    scheduled_at: datetime,
) -> ParticipationModeDelivery:
    existing = await session.scalar(
        select(ParticipationModeDelivery).where(
            ParticipationModeDelivery.idempotency_key == key
        )
    )
    if existing is not None:
        return existing
    row = ParticipationModeDelivery(
        user_id=user_id,
        kind=kind,
        idempotency_key=key,
        status="pending",
        scheduled_at=scheduled_at,
    )
    session.add(row)
    await session.flush()
    return row


async def _send(
    bot: Bot,
    delivery: ParticipationModeDelivery,
    *,
    chat_id: int,
    text: str,
) -> None:
    if delivery.status in {"sent", "blocked", "unreachable"}:
        return
    delivery.attempt_count += 1
    delivery.last_attempt_at = utcnow()
    try:
        await bot.send_message(chat_id, text)
    except TelegramForbiddenError:
        delivery.status = "blocked"
        delivery.error_code = "bot_blocked"
    except TelegramBadRequest:
        delivery.status = "unreachable"
        delivery.error_code = "telegram_unreachable"
    except TelegramAPIError:
        delivery.status = "failed"
        delivery.error_code = "telegram_delivery_failed"
    else:
        delivery.status = "sent"
        delivery.sent_at = utcnow()
        delivery.error_code = None


async def _process_pause_reminders(bot: Bot, session, now: datetime) -> None:
    today = now.astimezone().date()
    soon = today + timedelta(days=PAUSE_REMINDER_DAYS)
    rows = (
        await session.execute(
            select(User, ParticipationLifecycle)
            .join(ParticipationLifecycle, ParticipationLifecycle.user_id == User.id)
            .where(
                User.application_status == ApplicationStatus.APPROVED,
                User.is_archived.is_(False),
                User.is_blocked.is_(False),
                ParticipationLifecycle.participation_mode == MODE_PAUSED,
                ParticipationLifecycle.pause_until.is_not(None),
                ParticipationLifecycle.pause_until >= today,
                ParticipationLifecycle.pause_until <= soon,
            )
        )
    ).all()
    for user, lifecycle in rows:
        key = f"participation:pause_end:{user.id}:{lifecycle.pause_until.isoformat()}"
        delivery = await _delivery(
            session,
            user_id=user.id,
            kind="pause_end",
            key=key,
            scheduled_at=now,
        )
        await _send(
            bot,
            delivery,
            chat_id=user.telegram_id,
            text=(
                "Пауза в ЭРА скоро завершится.\n\n"
                f"Текущая дата возвращения: {lifecycle.pause_until.strftime('%d.%m.%Y')}. "
                "Можно вернуться раньше, продлить паузу или выбрать лёгкий режим — профиль, баллы и история сохраняются."
            ),
        )


async def _process_observer_checkins(bot: Bot, session, now: datetime) -> None:
    rows = (
        await session.execute(
            select(User, ParticipationLifecycle)
            .join(ParticipationLifecycle, ParticipationLifecycle.user_id == User.id)
            .where(
                User.application_status == ApplicationStatus.APPROVED,
                User.is_archived.is_(False),
                User.is_blocked.is_(False),
                ParticipationLifecycle.participation_mode == MODE_OBSERVER,
            )
        )
    ).all()
    today = now.astimezone().date()
    for user, lifecycle in rows:
        changed = lifecycle.mode_changed_at or lifecycle.state_since or user.created_at
        changed_date = changed.astimezone().date() if changed.tzinfo else changed.date()
        elapsed = (today - changed_date).days
        if elapsed < OBSERVER_CHECKIN_DAYS:
            continue
        period = elapsed // OBSERVER_CHECKIN_DAYS
        key = f"participation:observer:{user.id}:{period}"
        delivery = await _delivery(
            session,
            user_id=user.id,
            kind="observer_checkin",
            key=key,
            scheduled_at=now,
        )
        await _send(
            bot,
            delivery,
            chat_id=user.telegram_id,
            text=(
                "Небольшой check-in от ЭРА.\n\n"
                "Вы остаетесь в режиме наблюдателя — регулярных задач и напоминаний нет. "
                "Если захочется снова включиться, в профиле можно выбрать активный или лёгкий режим."
            ),
        )


async def process_participation_mode_notifications(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> None:
    now = utcnow()
    if _inside_quiet_hours(settings, now):
        return
    async with session_factory() as session:
        await _process_pause_reminders(bot, session, now)
        await _process_observer_checkins(bot, session, now)
        await session.commit()
