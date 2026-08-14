from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings
from app.services.chat_faq_service import ensure_general_faq_pinned
from app.services.system_health_service import run_system_diagnostics, send_daily_system_summary


def add_system_jobs(
    scheduler: AsyncIOScheduler,
    bot: Bot,
    settings: Settings,
    session_factory,
) -> None:
    """Attach production-health and durable chat-maintenance jobs."""

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
    # The FAQ is infrastructure for the general chat, not a one-off admin
    # broadcast. Run immediately after every deploy and then twice a day. The
    # service edits/re-pins the same recorded message, so this does not create
    # duplicate cards.
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
