from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings
from app.services.chat_faq_service import ensure_general_faq_pinned
from app.services.development_notification_service import send_monthly_development_reminders
from app.services.event_custom_reminder_service import send_configured_event_reminders
from app.services.event_wizard_sync_service import sync_event_wizard_tasks_job
from app.services.system_health_service import run_system_diagnostics, send_daily_system_summary


def add_system_jobs(
    scheduler: AsyncIOScheduler,
    bot: Bot,
    settings: Settings,
    session_factory,
) -> None:
    """Attach production-health jobs and durable infrastructure maintenance."""

    now = datetime.now(ZoneInfo(settings.timezone))
    scheduler.add_job(
        run_system_diagnostics,
        "interval",
        minutes=15,
        args=(bot, settings, session_factory),
        kwargs={"run_type": "heartbeat"},
        id="system-heartbeat",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=now,
    )
    scheduler.add_job(
        run_system_diagnostics,
        "interval",
        hours=4,
        args=(bot, settings, session_factory),
        kwargs={"run_type": "full"},
        id="system-full-diagnostic",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_daily_system_summary,
        "cron",
        hour=9,
        minute=30,
        args=(bot, settings, session_factory),
        id="system-daily-summary",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_configured_event_reminders,
        "interval",
        minutes=1,
        args=(bot, settings, session_factory),
        id="configured-event-reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        sync_event_wizard_tasks_job,
        "interval",
        minutes=1,
        args=(session_factory,),
        id="event-wizard-task-sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=now,
    )
    # This one idempotent daily pass now handles both the monthly Check-in
    # reminder and the optional weekly pulse. Keeping one job avoids another
    # moving part while still preventing duplicate sends after restarts.
    scheduler.add_job(
        send_monthly_development_reminders,
        "cron",
        hour=18,
        minute=0,
        args=(bot, settings, session_factory),
        id="my-vector-monthly-reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        ensure_general_faq_pinned,
        "interval",
        hours=12,
        args=(bot, settings, session_factory),
        id="general-chat-faq-pin",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=now,
    )
