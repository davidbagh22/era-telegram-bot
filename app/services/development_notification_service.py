from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from aiogram import Bot
from sqlalchemy import desc, select

from app.config import Settings
from app.database.development_models import (
    AssessmentConsent,
    DevelopmentAuditLog,
    MonthlyCheckin,
    WeeklyPulse,
)
from app.database.models import User
from app.services.bot_notification_service import PrimaryAction, send_bot_notification
from app.utils.constants import ApplicationStatus

REMINDER_ACTION = "development.monthly_checkin_reminder.sent"
WEEKLY_PULSE_ACTION = "development.weekly_pulse_reminder.sent"


async def _eligible_users(session) -> list[User]:
    return list(
        (
            await session.scalars(
                select(User).where(
                    User.application_status == ApplicationStatus.APPROVED,
                    User.is_archived.is_(False),
                    User.is_blocked.is_(False),
                )
            )
        ).all()
    )


async def _has_active_consent(session, user_id: int) -> bool:
    consent = await session.scalar(
        select(AssessmentConsent)
        .where(AssessmentConsent.user_id == user_id)
        .order_by(desc(AssessmentConsent.created_at), desc(AssessmentConsent.id))
        .limit(1)
    )
    return bool(consent and consent.accepted)


async def send_monthly_development_reminders(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> None:
    """Send monthly Check-in reminders, then run the idempotent weekly pulse pass."""
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with session_factory() as session:
        for user in await _eligible_users(session):
            if not await _has_active_consent(session, user.id):
                continue
            completed = await session.scalar(
                select(MonthlyCheckin.id).where(
                    MonthlyCheckin.user_id == user.id,
                    MonthlyCheckin.month == month,
                    MonthlyCheckin.status == "completed",
                )
            )
            if completed is not None:
                continue
            already_sent = await session.scalar(
                select(DevelopmentAuditLog.id).where(
                    DevelopmentAuditLog.target_user_id == user.id,
                    DevelopmentAuditLog.action == REMINDER_ACTION,
                    DevelopmentAuditLog.created_at >= month_start,
                )
            )
            if already_sent is not None:
                continue

            sent = await send_bot_notification(
                bot,
                user.telegram_id,
                emoji="🧭",
                title="Новый месяц — новая карта вектора",
                body=(
                    "Ты уже прошёл путь, который не виден снаружи. "
                    "Короткая отметка в «Мой вектор» покажет сдвиг по энергии, "
                    "действию и направлению — и подскажет один следующий шаг."
                ),
                footer="Без оценок и штрафов. Можно начать сейчас и дописать позже.",
                action=PrimaryAction(label="Пройти отметку", callback_data="vector:start"),
                settings=settings,
                delivery_key=f"development-monthly:{month}:{user.id}",
                notification_type="development_monthly_checkin",
            )
            if not sent:
                continue
            session.add(
                DevelopmentAuditLog(
                    actor_user_id=None,
                    target_user_id=user.id,
                    action=REMINDER_ACTION,
                    metadata_json={"month": month},
                )
            )
        await session.commit()

    # The scheduler already runs this function daily. The weekly pass reuses a
    # stable delivery key, so a restart between Telegram send and audit commit
    # completes the marker without creating a second message.
    await send_weekly_development_pulses(bot, settings, session_factory)


async def send_weekly_development_pulses(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> None:
    """Offer one optional energy pulse each week to consenting participants."""
    now = datetime.now(timezone.utc)
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    week_start_dt = datetime.combine(week_start, time.min, tzinfo=timezone.utc)

    async with session_factory() as session:
        for user in await _eligible_users(session):
            if not await _has_active_consent(session, user.id):
                continue
            existing_pulse = await session.scalar(
                select(WeeklyPulse.id).where(
                    WeeklyPulse.user_id == user.id,
                    WeeklyPulse.week_start == week_start,
                )
            )
            if existing_pulse is not None:
                continue
            already_sent = await session.scalar(
                select(DevelopmentAuditLog.id).where(
                    DevelopmentAuditLog.target_user_id == user.id,
                    DevelopmentAuditLog.action == WEEKLY_PULSE_ACTION,
                    DevelopmentAuditLog.created_at >= week_start_dt,
                )
            )
            if already_sent is not None:
                continue

            # Prefer the monthly vector survey when it is still open — that is
            # what reshapes the radar. Otherwise offer a one-tap energy pulse.
            month = now.strftime("%Y-%m")
            monthly_done = await session.scalar(
                select(MonthlyCheckin.id).where(
                    MonthlyCheckin.user_id == user.id,
                    MonthlyCheckin.month == month,
                    MonthlyCheckin.status == "completed",
                )
            )
            if monthly_done is None:
                sent = await send_bot_notification(
                    bot,
                    user.telegram_id,
                    emoji="🧭",
                    title="Твой вектор ждёт новую точку",
                    body=(
                        "За неделю многое могло сдвинуться — энергия, связи, "
                        "направление. Три минуты в «Мой вектор», и карта снова "
                        "станет честной: без оценок, без гонки, только ты и рост."
                    ),
                    footer="Можно остановиться в любой момент и продолжить позже.",
                    action=PrimaryAction(label="Обновить вектор", callback_data="vector:start"),
                    settings=settings,
                    delivery_key=f"development-weekly:{week_start.isoformat()}:{user.id}",
                    notification_type="development_weekly_pulse",
                )
            else:
                sent = await send_bot_notification(
                    bot,
                    user.telegram_id,
                    emoji="⚡",
                    title="Пульс недели",
                    body=(
                        "Месячная отметка уже есть — круто. "
                        "Один короткий ответ про энергию удержит динамику живой."
                    ),
                    footer="Необязательно. Только для твоей личной карты.",
                    action=PrimaryAction(label="Отметить состояние", callback_data="vector:pulse:start"),
                    settings=settings,
                    delivery_key=f"development-weekly:{week_start.isoformat()}:{user.id}",
                    notification_type="development_weekly_pulse",
                )
            if not sent:
                continue
            session.add(
                DevelopmentAuditLog(
                    actor_user_id=None,
                    target_user_id=user.id,
                    action=WEEKLY_PULSE_ACTION,
                    metadata_json={"week_start": week_start.isoformat()},
                )
            )
        await session.commit()
