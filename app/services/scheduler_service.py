import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import Settings
from app.database.models import Event, EventRegistration, User
from app.services.event_service import event_datetime
from app.services.notification_service import safe_send
from app.utils.constants import EventStatus, RegistrationStatus

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
            elif event.selfie_required:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Отправить селфи",
                                callback_data=f"selfie:start:{event.id}",
                            )
                        ]
                    ]
                )
                await safe_send(
                    bot,
                    user.telegram_id,
                    f"Мероприятие «{event.title}» завершилось. Если Вы были на месте, отправьте селфи-подтверждение.",
                    keyboard,
                )
            registration.reminder_stage = target_stage
            registration.last_reminder_at = now
        await session.commit()


async def send_weekly_message(bot: Bot, chat_id: int, text: str) -> None:
    await safe_send(bot, chat_id, text)


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
