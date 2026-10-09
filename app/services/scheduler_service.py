from app.services.leaders_workspace import deadline_label
import logging
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import Settings
from app.services.general_topics_service import send_general_topic
from app.database.event_experience import EventExperience
from app.database.management_models import AdminSurvey
from app.database.models import (
    Event,
    EventRegistration,
    Project,
    Task,
    TaskDelivery,
    TaskParticipant,
    User,
)
from app.keyboards.admin import project_review_actions
from app.services.birthday_service import send_birthday_greetings
from app.services.bot_notification_service import PrimaryAction, send_bot_notification
from app.services.event_service import event_datetime
from app.services.general_chat_content_service import run_scheduled_slot
from app.services.notification_service import (
    BroadcastResult,
    admin_notification_recipients,
    broadcast_detailed_once,
    safe_send_once,
)
from app.services.survey_service import (
    MONTHLY_SURVEY_DESCRIPTION,
    MONTHLY_SURVEY_QUESTIONS,
    MONTHLY_SURVEY_TITLE,
    questions_payload,
)
from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus, RegistrationStatus
from app.utils.deep_links import miniapp_event_url, miniapp_task_url

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


def _delivery_finished(result: BroadcastResult) -> bool:
    """A scheduled stage is complete only when no transient recipient remains."""
    completed = result.sent + result.permanent_failed + result.duplicates
    return result.temporary_failed == 0 and completed > 0


def _reminder_lead(stage: int) -> str:
    if stage == 1:
        return "Завтра встречаемся"
    if stage == 2:
        return "До события около 3 часов"
    return "Событие скоро начнётся"


async def send_event_reminders(bot: Bot, settings: Settings, session_factory) -> None:
    """Compatibility reminder for events without configured wizard reminders.

    Rich events use event_custom_reminder_service. Historical events use this
    fallback. Every user/stage has a durable delivery key, so scheduler retries
    and process restarts cannot create duplicate Telegram messages.
    """
    now = datetime.now(ZoneInfo(settings.timezone))
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(EventRegistration, Event, User)
                .join(Event, Event.id == EventRegistration.event_id)
                .join(User, User.id == EventRegistration.user_id)
                .where(
                    Event.status.in_([
                        EventStatus.APPROVED,
                        EventStatus.PUBLISHED,
                        EventStatus.REGISTRATION_OPEN,
                    ]),
                    EventRegistration.status.in_(
                        [RegistrationStatus.REGISTERED, RegistrationStatus.WILL_COME]
                    ),
                )
            )
        ).all()
        for registration, event, user in rows:
            experience = await session.get(EventExperience, event.id)
            if experience is not None and list(experience.reminders or []):
                continue

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
            if target_stage <= 3:
                await send_general_topic(
                    bot, settings, "announcements",
                    f"⏰ {_reminder_lead(target_stage)}\n\n{event.title}\n"
                    f"📅 {event.event_date:%d.%m.%Y} · {event.event_time:%H:%M}\n📍 {event.location}",
                    delivery_key=f"event:{event.id}:legacy-reminder:{target_stage}:{event.event_date}:{event.event_time}",
                )
            if registration.reminder_stage >= target_stage:
                continue

            if target_stage <= 3:
                url = miniapp_event_url(settings.effective_miniapp_url, event.id)
                action = (
                    PrimaryAction(label="Открыть мероприятие", web_app_url=url)
                    if url
                    else PrimaryAction(
                        label="Открыть мероприятие",
                        callback_data=f"event:view:{event.id}",
                    )
                )
                sent = await send_bot_notification(
                    bot,
                    user.telegram_id,
                    emoji="🔥",
                    title=_reminder_lead(target_stage),
                    body=(
                        f"{event.title}\n\n"
                        f"📅 {event.event_date:%d.%m.%Y} · {event.event_time:%H:%M}\n"
                        f"📍 {event.location}"
                    ),
                    footer=(
                        "Если планы изменились — отмените участие заранее, чтобы место мог занять другой участник."
                    ),
                    action=action,
                    settings=settings,
                    delivery_key=(
                        f"event-reminder:{event.id}:{registration.id}:{target_stage}"
                    ),
                    notification_type="event_reminder",
                )
                if not sent:
                    continue
            registration.reminder_stage = target_stage
            registration.last_reminder_at = now
        await session.commit()


async def send_weekly_message(
    bot: Bot,
    settings: Settings,
    chat_id: int,
    text: str,
    chat_key: str,
) -> None:
    now = datetime.now(ZoneInfo(settings.timezone))
    iso_year, iso_week, _ = now.isocalendar()
    if chat_key == "general":
        await send_general_topic(bot, settings, "notifications", text, delivery_key=f"weekly:{iso_year}-W{iso_week:02d}")
        return
    await safe_send_once(
        bot,
        settings,
        chat_id,
        text,
        delivery_key=f"weekly-chat:{chat_key}:{iso_year}-W{iso_week:02d}",
        notification_type="weekly_chat",
    )


async def send_monthly_surveys(bot: Bot, settings: Settings, session_factory) -> None:
    """Send the monthly management pulse survey once per recipient/month."""
    now = datetime.now(ZoneInfo(settings.timezone))
    current_month = now.strftime("%Y-%m")
    async with session_factory() as session:
        surveys = list(
            (
                await session.scalars(
                    select(AdminSurvey)
                    .where(AdminSurvey.is_monthly.is_(True), AdminSurvey.status != "archived")
                    .order_by(AdminSurvey.created_at.desc(), AdminSurvey.id.desc())
                )
            ).all()
        )
        survey = next((item for item in surveys if item.last_sent_month != current_month), None)
        if not survey:
            survey = AdminSurvey(
                title=MONTHLY_SURVEY_TITLE,
                description=MONTHLY_SURVEY_DESCRIPTION,
                questions_json=questions_payload(MONTHLY_SURVEY_QUESTIONS),
                audience_type="approved",
                audience_filter_json={},
                status="draft",
                is_monthly=True,
            )
            session.add(survey)
            await session.flush()
        recipients = list(
            (
                await session.scalars(
                    select(User).where(
                        User.application_status == ApplicationStatus.APPROVED,
                        User.is_blocked.is_(False),
                        User.is_archived.is_(False),
                    )
                )
            ).all()
        )
        if not recipients:
            await session.commit()
            return
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="Ответить на опрос",
                    callback_data=f"survey:start:{survey.id}",
                )
            ]]
        )
        result = await broadcast_detailed_once(
            bot,
            settings,
            [participant.telegram_id for participant in recipients],
            f"🗳 {survey.title}\n\n{survey.description}\n\nОтвет займёт несколько минут",
            delivery_key=f"monthly-survey:{survey.id}:{current_month}",
            notification_type="monthly_survey",
            reply_markup=keyboard,
        )
        if not _delivery_finished(result):
            logger.warning(
                "Monthly survey delivery postponed: sent=%s failed=%s temporary=%s duplicates=%s",
                result.sent,
                result.failed,
                result.temporary_failed,
                result.duplicates,
            )
            await session.commit()
            return
        survey.status = "sent"
        survey.sent_at = now
        survey.last_sent_month = current_month
        await session.commit()


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
            stage = project.venue_reminder_count + 1
            text = (
                f"⏳ Нужно решение по площадке\n\n"
                f"Проект: {project.title}\n"
                f"Автор: {author_name}\n"
                f"Напоминание {stage} из 5\n\n"
                "Выберите решение или перенесите напоминание"
            )
            result = await broadcast_detailed_once(
                bot,
                settings,
                await admin_notification_recipients(settings),
                text,
                delivery_key=f"project-venue-reminder:{project.id}:{stage}",
                notification_type="project_venue_reminder",
                reply_markup=project_review_actions(project.id, ProjectStatus.VENUE_REVIEW),
            )
            if not _delivery_finished(result):
                continue
            project.venue_reminder_count += 1
            project.venue_remind_at = (
                now + timedelta(days=1) if project.venue_reminder_count < 5 else None
            )
        await session.commit()


async def send_task_reminders(bot: Bot, settings: Settings, session_factory) -> None:
    """Send task deadline reminders with durable per-recipient stage keys."""
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

            url = miniapp_task_url(settings.effective_miniapp_url, task.id)
            action = (
                PrimaryAction(label="Открыть задачу", web_app_url=url)
                if url
                else None
            )
            stage = task.reminder_count + 1
            expected_recipients = 0
            completed_recipients = 0
            for user_id in participant_ids:
                target = await session.get(User, user_id)
                if target is None or target.is_blocked or target.is_archived:
                    continue
                expected_recipients += 1
                sent = await send_bot_notification(
                    bot,
                    target.telegram_id,
                    emoji="⏳",
                    title="Дедлайн приближается",
                    body=(
                        f"{task.title}\n\n"
                        f"До: {deadline_label(task.deadline, '%d.%m.%Y %H:%M')}"
                    ),
                    footer="Если задача уже готова — отправьте результат из карточки задачи.",
                    action=action,
                    settings=settings,
                    delivery_key=f"task-reminder:{task.id}:{stage}:user:{target.id}",
                    notification_type="task_reminder",
                )
                completed_recipients += int(sent)

            creator = await session.get(User, task.creator_id)
            if creator is not None and creator.id not in participant_ids and not creator.is_blocked and not creator.is_archived:
                expected_recipients += 1
                sent = await send_bot_notification(
                    bot,
                    creator.telegram_id,
                    emoji="⏳",
                    title="По задаче приближается дедлайн",
                    body=(
                        f"{task.title}\n\n"
                        f"До: {deadline_label(task.deadline, '%d.%m.%Y %H:%M')}"
                    ),
                    footer="Откройте карточку, чтобы проверить состояние работы.",
                    action=action,
                    settings=settings,
                    delivery_key=f"task-reminder:{task.id}:{stage}:creator:{creator.id}",
                    notification_type="task_reminder",
                )
                completed_recipients += int(sent)

            # The Leaders workspace has one authoritative task card per
            # group/topic. Keep its thread members in the same reminder loop
            # as private recipients, with durable per-card stage tracking.
            leader_deliveries = (
                await session.scalars(
                    select(TaskDelivery).where(
                        TaskDelivery.task_id == task.id,
                        TaskDelivery.chat_key == "leaders",
                        TaskDelivery.status == "sent",
                        TaskDelivery.remind_at.is_not(None),
                        TaskDelivery.remind_at <= now,
                        TaskDelivery.reminder_count < 5,
                    )
                )
            ).all()
            for delivery in leader_deliveries:
                assignee = await session.get(User, task.assignee_id) if task.assignee_id else None
                label = escape(
                    f"{assignee.first_name} {assignee.last_name or ''}".strip()
                    if assignee
                    else "Исполнитель"
                )
                mention = (
                    f"@{escape(assignee.username)}"
                    if assignee and assignee.username
                    else (
                        f'<a href="tg://user?id={assignee.telegram_id}">{label}</a>'
                        if assignee
                        else label
                    )
                )
                stage = delivery.reminder_count + 1
                try:
                    await bot.send_message(
                        chat_id=delivery.chat_id,
                        message_thread_id=delivery.message_thread_id,
                        text=(
                            f"⏳ <b>Напоминание по задаче #{task.id} · {stage}/5</b>\n"
                            f"{mention}, срок: {deadline_label(task.deadline, '%d.%m.%Y %H:%M')}.\n"
                            f"Задача: {escape(task.title)}"
                        ),
                        parse_mode="HTML",
                    )
                except TelegramAPIError as exc:
                    logger.warning("Could not send Leaders reminder for task %s: %s", task.id, exc)
                    continue
                delivery.reminder_count = stage
                delivery.remind_at = now + timedelta(days=1) if stage < 5 else None

            if expected_recipients and completed_recipients < expected_recipients:
                continue
            task.reminder_count += 1
            task.remind_at = (
                now + timedelta(days=1) if task.reminder_count < 5 else None
            )
        await session.commit()


TRAJECTORY_BROADCAST_DATES = (5, 12, 19, 26, 30)
TRAJECTORY_CHAT_URL = "https://t.me/+Vz588wqkyt82ZTRi"
TRAJECTORY_TEXT = """📢 Приглашаем молодых соотечественников на образовательную программу Международного научно-просветительского форума «Траектория открытий»!

📅 31 октября 2026 года · 10:00–13:30
📍 Дом Москвы в Ереване
⭐ За подтверждённое посещение — 150 баллов ЭРА

В программе:
10:00–10:15 — Открытие
10:15–11:30 — «Как развивать критическое мышление в эпоху ИИ»
11:30–12:00 — Кофе-брейк
12:00–13:15 — «Историческая правда и фейки: как работать с источниками»
13:15–13:30 — Завершение

🎓 Все участники получат сертификаты.

Для участия зарегистрируйтесь на мероприятие в ЭРА и обязательно присоединитесь к общему чату — там будет вся дальнейшая информация:
https://t.me/+Vz588wqkyt82ZTRi"""


async def send_trajectory_campaign(bot: Bot, settings: Settings, session_factory) -> None:
    """Five idempotent campaign waves before the 31 Oct 2026 event."""
    now = datetime.now(ZoneInfo(settings.timezone))
    if now.year != 2026 or now.month != 10 or now.day > 30:
        return
    due = [day for day in TRAJECTORY_BROADCAST_DATES if day <= now.day]
    if not due:
        return
    stage = len(due)
    async with session_factory() as session:
        recipients = list((await session.scalars(
            select(User).where(
                User.application_status == ApplicationStatus.APPROVED,
                User.is_blocked.is_(False),
                User.is_archived.is_(False),
            )
        )).all())
        await broadcast_detailed_once(
            bot, settings, [u.telegram_id for u in recipients], TRAJECTORY_TEXT,
            delivery_key=f"trajectory-20261031:personal:{stage}",
            notification_type="event_campaign",
        )
        chat_ids = {
            "general": settings.general_chat_id,
            "internal": settings.internal_department_chat_id,
            "external": settings.external_department_chat_id,
            "leaders": settings.leaders_chat_id,
        }
        for chat_key, chat_id in chat_ids.items():
            if chat_key == "general":
                await send_general_topic(bot, settings, "announcements", TRAJECTORY_TEXT, delivery_key=f"trajectory:{stage}")
                continue
            if chat_id:
                await safe_send_once(
                    bot, settings, int(chat_id), TRAJECTORY_TEXT,
                    delivery_key=f"trajectory-20261031:v2:{chat_key}:{stage}",
                    notification_type="event_campaign",
                )
        await session.commit()


async def send_general_content_morning(
    bot: Bot, settings: Settings, session_factory
) -> None:
    await run_scheduled_slot(bot, settings, session_factory, "morning")


async def send_general_content_evening(
    bot: Bot, settings: Settings, session_factory
) -> None:
    await run_scheduled_slot(bot, settings, session_factory, "evening")


async def recover_general_content(bot: Bot, settings: Settings, session_factory) -> None:
    """Recover only today's due slots; idempotency prevents any restart flood."""
    now = datetime.now(ZoneInfo(settings.timezone))
    if (now.hour, now.minute) >= (9, 0):
        await run_scheduled_slot(bot, settings, session_factory, "morning", now=now)
    if (now.hour, now.minute) >= (18, 0):
        await run_scheduled_slot(bot, settings, session_factory, "evening", now=now)


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
        send_birthday_greetings,
        "cron",
        hour=10,
        minute=0,
        args=(bot, settings, session_factory),
        id="birthday-greetings",
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
    scheduler.add_job(
        send_trajectory_campaign,
        "interval",
        minutes=15,
        args=(bot, settings, session_factory),
        id="trajectory-20261031-campaign",
        next_run_time=datetime.now(ZoneInfo(settings.timezone)),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_monthly_surveys,
        "cron",
        day=1,
        hour=11,
        minute=0,
        args=(bot, settings, session_factory),
        id="monthly-surveys",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_general_content_morning,
        "cron",
        hour=9,
        minute=0,
        args=(bot, settings, session_factory),
        id="general-content-morning",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_general_content_evening,
        "cron",
        hour=18,
        minute=0,
        args=(bot, settings, session_factory),
        id="general-content-evening",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        recover_general_content,
        "interval",
        minutes=30,
        args=(bot, settings, session_factory),
        id="general-content-recovery",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # General chat has its own two-slot editorial ritual. Department/leader
    # operational nudges remain separate, but are now durable per ISO week.
    weekly_targets = (
        (
            settings.internal_department_chat_id,
            WEEKLY_MESSAGES["internal"],
            "internal",
            "weekly-internal",
        ),
        (
            settings.external_department_chat_id,
            WEEKLY_MESSAGES["external"],
            "external",
            "weekly-external",
        ),
        (
            settings.leaders_chat_id,
            WEEKLY_MESSAGES["leaders"],
            "leaders",
            "weekly-leaders",
        ),
    )
    for chat_id, message, chat_key, job_id in weekly_targets:
        if chat_id:
            scheduler.add_job(
                send_weekly_message,
                "cron",
                day_of_week="mon",
                hour=10,
                minute=0,
                args=(bot, settings, int(chat_id), message, chat_key),
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
    return scheduler
