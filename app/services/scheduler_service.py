import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import Settings
from app.database.models import (
    Event,
    EventRegistration,
    Project,
    Task,
    TaskParticipant,
    User,
)
from app.keyboards.admin import project_review_actions
from app.services.archive_service import archive_expired_content
from app.services.event_service import event_datetime
from app.services.notification_service import safe_send
from app.utils.constants import EventStatus, ProjectStatus, RegistrationStatus

logger = logging.getLogger(__name__)

WEEKLY_MESSAGES = {
    "general": (
        "Новая неделя в ЭРА. Посмотрите ближайшие мероприятия, проверьте свои задачи и выберите один конкретный шаг, который усилит Ваш путь в команде."
    ),
    "internal": (
        "Неделя внутренних связей начинается с действий. Предложите идею, возьмите задачу или помогите команде подготовить ближайшее мероприятие."
    ),
    "external": (
        "Новая неделя во внешних связях. Если Вы видите возможность для медиа, партнёрства, международного проекта или социальной инициативы — зафиксируйте её и предложите команде."
    ),
    "leaders": (
        "Лидерская сверка недели: проверьте участников, задачи, проекты, мероприятия и отчёты. Определите, кому нужна поддержка и какой результат должен быть достигнут к концу недели."
    ),
}


def _reminder_text(event: Event, stage: int) -> str:
    if stage == 1:
        lead = "Напоминание. Завтра состоится мероприятие:"
    elif stage == 2:
        lead = "До мероприятия осталось около 3 часов:"
    else:
        lead = "Мероприятие скоро начнётся:"
    return (
        f"{lead}\n\n{event.title}\n\nДата: {event.event_date:%d.%m.%Y}\n"
        f"Время: {event.event_time:%H:%M}\nМесто: {event.location}\n\nВы сможете прийти?"
    )


async def send_event_reminders(bot: Bot, settings: Settings, session_factory) -> None:
    now = datetime.now(ZoneInfo(settings.timezone))
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(EventRegistration, Event, User)
                .join(Event, Event.id == EventRegistration.event_id)
                .join(User, User.id == EventRegistration.user_id)
                .where(
                    Event.status.in_([EventStatus.APPROVED, EventStatus.PUBLISHED]),
                    EventRegistration.status.in_(
                        [RegistrationStatus.REGISTERED, RegistrationStatus.WILL_COME]
                    ),
                )
            )
        ).all()
        for registration, event, user in rows:
            delta = event_datetime(event, settings.timezone) - now
            if timedelta(hours=3) < delta <= timedelta(hours=24):
                target_stage = 1
            elif timedelta(minutes=30) < delta <= timedelta(hours=3):
                target_stage = 2
            elif timedelta(0) < delta <= timedelta(minutes=30):
                target_stage = 3
            elif -timedelta(hours=24) <= delta <= timedelta(0):
                target_stage = 4
            else:
                continue
            if registration.reminder_stage >= target_stage:
                continue
            if target_stage <= 3:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Да, приду",
                                callback_data=f"attendance:{event.id}:yes",
                            ),
                            InlineKeyboardButton(
                                text="Нет, не смогу",
                                callback_data=f"attendance:{event.id}:no",
                            ),
                        ]
                    ]
                )
                await safe_send(
                    bot, user.telegram_id, _reminder_text(event, target_stage), keyboard
                )
            registration.reminder_stage = target_stage
            registration.last_reminder_at = now
        await session.commit()


async def send_weekly_message(bot: Bot, chat_id: int, text: str) -> None:
    await safe_send(bot, chat_id, text)


async def run_archive_maintenance(settings: Settings, session_factory) -> None:
    async with session_factory() as session:
        result = await archive_expired_content(session, timezone=settings.timezone)
        await session.commit()
    logger.info("archive-maintenance completed: %s", result)


async def send_project_venue_reminders(
    bot: Bot, settings: Settings, session_factory
) -> None:
    """Remind administrators about venue decisions, at most five times per project."""
    now = datetime.now(ZoneInfo(settings.timezone))
    async with session_factory() as session:
        projects = (
            await session.scalars(
                select(Project).where(
                    Project.status == ProjectStatus.VENUE_REVIEW,
                    Project.venue_reminder_count < 5,
                    Project.venue_remind_at.is_not(None),
                    Project.venue_remind_at <= now,
                )
            )
        ).all()
        for project in projects:
            author = await session.get(User, project.author_id)
            author_name = (
                f"{author.first_name} {author.last_name or ''}".strip()
                if author
                else f"ID {project.author_id}"
            )
            text = (
                f"⏳ Нужно решение по площадке\n\n"
                f"Проект: {project.title}\n"
                f"Автор: {author_name}\n"
                f"Напоминание {project.venue_reminder_count + 1} из 5\n\n"
                "Выберите решение или перенесите напоминание"
            )
            for telegram_id in settings.admin_ids:
                await safe_send(
                    bot,
                    telegram_id,
                    text,
                    project_review_actions(project.id, ProjectStatus.VENUE_REVIEW),
                )
            project.venue_reminder_count += 1
            project.venue_remind_at = (
                now + timedelta(days=1) if project.venue_reminder_count < 5 else None
            )
        await session.commit()


async def send_task_reminders(bot: Bot, settings: Settings, session_factory) -> None:
    now = datetime.now(ZoneInfo(settings.timezone))
    async with session_factory() as session:
        tasks = (
            await session.scalars(
                select(Task).where(
                    Task.status.in_(["new", "published", "in_progress"]),
                    Task.remind_at.is_not(None),
                    Task.remind_at <= now,
                    Task.deadline > now,
                    Task.reminder_count < 5,
                )
            )
        ).all()
        for task in tasks:
            participant_ids = set(
                (
                    await session.scalars(
                        select(TaskParticipant.user_id).where(
                            TaskParticipant.task_id == task.id
                        )
                    )
                ).all()
            )
            if task.assignee_id:
                participant_ids.add(task.assignee_id)
            for user_id in participant_ids:
                target = await session.get(User, user_id)
                if target:
                    await safe_send(
                        bot,
                        target.telegram_id,
                        f"⏳ Напоминание о задании\n\n{task.title}\n\n"
                        f"Дедлайн: {task.deadline:%d.%m.%Y %H:%M}\n"
                        "Откройте «Мой путь» → «Мои задания», чтобы продолжить",
                    )
            creator = await session.get(User, task.creator_id)
            if creator:
                await safe_send(
                    bot,
                    creator.telegram_id,
                    f"⏳ По заданию «{task.title}» приближается дедлайн: "
                    f"{task.deadline:%d.%m.%Y %H:%M}",
                )
            task.reminder_count += 1
            task.remind_at = (
                now + timedelta(days=1) if task.reminder_count < 5 else None
            )
        await session.commit()


def create_scheduler(bot: Bot, settings: Settings, session_factory) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        send_event_reminders,
        "interval",
        minutes=1,
        args=(bot, settings, session_factory),
        id="event-reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_archive_maintenance,
        "interval",
        hours=6,
        args=(settings, session_factory),
        id="archive-maintenance",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_project_venue_reminders,
        "interval",
        minutes=15,
        args=(bot, settings, session_factory),
        id="project-venue-reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_task_reminders,
        "interval",
        minutes=15,
        args=(bot, settings, session_factory),
        id="task-reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    weekly_targets = (
        (settings.general_chat_id, WEEKLY_MESSAGES["general"], "weekly-general"),
        (
            settings.internal_department_chat_id,
            WEEKLY_MESSAGES["internal"],
            "weekly-internal",
        ),
        (
            settings.external_department_chat_id,
            WEEKLY_MESSAGES["external"],
            "weekly-external",
        ),
        (settings.leaders_chat_id, WEEKLY_MESSAGES["leaders"], "weekly-leaders"),
    )
    for chat_id, message, job_id in weekly_targets:
        if chat_id:
            scheduler.add_job(
                send_weekly_message,
                "cron",
                day_of_week="mon",
                hour=10,
                minute=0,
                args=(bot, chat_id, message),
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
    return scheduler
