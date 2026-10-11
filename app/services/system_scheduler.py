from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings
from app.services.chat_permissions_service import enforce_general_chat_writable
from app.services.community_mission_service import process_task_squad_notifications
from app.services.community_verification_jobs import complete_verification_campaigns_job
from app.services.daily_public_content_service import run_daily_public_content
from app.services.development_notification_service import send_monthly_development_reminders
from app.services.event_custom_reminder_service import send_configured_event_reminders
from app.services.event_wizard_sync_service import sync_event_wizard_tasks_job
from app.services.leadership_weekly_service import check_weekly_pulses_job, open_weekly_pulses_job
from app.services.leaders_workcenter_service import sync_leaders_task_cards
from app.services.leaders_topics_service import setup_leaders_topics
from app.services.general_topics_service import setup_general_topics
from app.services.weekly_pulse_archive_service import archive_due_cycles
from app.services.media_attachment_service import post_missing_media_task_cards
from app.services.media_pipeline_service import reconcile_media_pipeline_job
from app.services.media_service import process_media_chat_automation, publish_due_channel_content
from app.services.participation_lifecycle_service import run_reactivation_cycle
from app.services.project_scoring_reconciliation_service import reconcile_project_scoring_job
from app.services.system_health_service import run_system_diagnostics, send_daily_system_summary
from app.services.vacancy_reconciliation_service import reconcile_vacancies_job
from app.services.admin_broadcast_service import resume_broadcasts
from app.services.book_club_service import daily_job as book_club_daily_job
from app.services.literature_launch_service import publish_literature_launch
from app.services.literature_channel_announcement import publish_literature_channel_launch
from app.services.literature_analytics_service import send_literature_admin_digest
from app.services.directions_announcement import publish_directions_announcement
from app.services.games_launch_service import publish_games_launch
from app.services.game_room_expiry_service import expire_game_rooms


def add_system_jobs(
    scheduler: AsyncIOScheduler,
    bot: Bot,
    settings: Settings,
    session_factory,
) -> None:
    """Attach production-health jobs and durable infrastructure maintenance."""
    now = datetime.now(ZoneInfo(settings.timezone))

    for job_id in (
        "general-content-morning",
        "general-content-evening",
        "general-content-recovery",
    ):
        if scheduler.get_job(job_id) is not None:
            scheduler.remove_job(job_id)

    scheduler.add_job(run_system_diagnostics, "interval", minutes=15, args=(bot, settings, session_factory), kwargs={"run_type": "heartbeat"}, id="system-heartbeat", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(run_system_diagnostics, "interval", hours=4, args=(bot, settings, session_factory), kwargs={"run_type": "full"}, id="system-full-diagnostic", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(send_daily_system_summary, "cron", hour=9, minute=30, args=(bot, settings, session_factory), id="system-daily-summary", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(reconcile_vacancies_job, "interval", minutes=30, args=(session_factory,), id="office-vacancy-reconciliation", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(send_configured_event_reminders, "interval", minutes=1, args=(bot, settings, session_factory), id="configured-event-reminders", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(sync_event_wizard_tasks_job, "interval", minutes=1, args=(session_factory,), id="event-wizard-task-sync", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(reconcile_project_scoring_job, "interval", minutes=1, args=(session_factory,), id="project-scoring-reconciliation", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(process_task_squad_notifications, "interval", minutes=1, args=(bot, settings, session_factory), id="task-squad-notifications", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(reconcile_media_pipeline_job, "interval", minutes=1, args=(session_factory,), id="media-content-pipeline-reconciliation", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(publish_due_channel_content, "interval", minutes=1, args=(bot, settings, session_factory), id="media-channel-publication", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(post_missing_media_task_cards, "interval", minutes=1, args=(bot, settings, session_factory), id="media-task-cards", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(process_media_chat_automation, "interval", minutes=1, args=(bot, settings, session_factory), id="media-chat-automation", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(run_reactivation_cycle, "interval", hours=1, args=(bot, settings, session_factory), id="participation-reactivation", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(complete_verification_campaigns_job, "interval", minutes=5, args=(session_factory,), id="community-verification-expiry", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(send_monthly_development_reminders, "cron", hour=18, minute=0, args=(bot, settings, session_factory), id="my-vector-monthly-reminders", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(book_club_daily_job, "cron", hour=19, minute=0, args=(bot, settings, session_factory), id="book-club-daily", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(publish_literature_launch, "interval", minutes=5, args=(bot, settings, session_factory), id="literature-opening-recovery", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(publish_literature_channel_launch, "interval", minutes=5, args=(bot, settings), id="literature-channel-opening", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(send_literature_admin_digest, "cron", hour=20, minute=0, args=(bot, settings, session_factory), id="literature-admin-digest", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(resume_broadcasts, "interval", minutes=1, args=(bot, settings, session_factory), id="admin-broadcast-resume", replace_existing=True, max_instances=1, coalesce=True)

    scheduler.add_job(
        run_daily_public_content,
        "interval",
        minutes=5,
        args=(bot, settings, session_factory),
        id="era-daily-public-content",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=now,
    )

    scheduler.add_job(
        enforce_general_chat_writable,
        "interval",
        minutes=5,
        args=(bot, settings, session_factory),
        id="general-chat-writable-access",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=now,
    )

    scheduler.add_job(open_weekly_pulses_job, "interval", minutes=5, args=(bot, settings, session_factory), id="leadership-weekly-pulse-open", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(check_weekly_pulses_job, "interval", minutes=5, args=(bot, settings, session_factory), id="leadership-weekly-pulse-due", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(sync_leaders_task_cards, "interval", minutes=1, args=(bot, settings, session_factory), id="leaders-task-card-sync", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)

    scheduler.add_job(setup_general_topics, "interval", minutes=5, args=(bot, settings, session_factory), id="general-forum-setup", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(expire_game_rooms, "interval", minutes=1, args=(session_factory,), id="era-games-expiry", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(publish_games_launch, "interval", minutes=5, args=(bot, settings, session_factory), id="era-games-launch", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
    scheduler.add_job(publish_directions_announcement, "interval", minutes=5, args=(bot, settings), id="directions-one-time-announcement", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)

    scheduler.add_job(setup_leaders_topics, "interval", minutes=5, args=(bot, settings, session_factory), id="leaders-forum-setup", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)

    scheduler.add_job(archive_due_cycles, "interval", minutes=5, args=(bot, settings, session_factory), id="pulse-weekly-archive", replace_existing=True, max_instances=1, coalesce=True, next_run_time=now)
