from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.database.management_models import AdminSurvey, AdminSurveyResponse
from app.database.models import User
from app.services.notification_service import safe_send_once
from app.utils.constants import ApplicationStatus
from app.utils.deep_links import miniapp_path_url

logger = logging.getLogger(__name__)

SURVEY_ID = 13
DELIVERY_VERSION = "v1"

REMINDER_TEXT = (
    "🔥 Помоги нам собрать программу конференции ЭРА\n\n"
    "Мы готовим молодёжную конференцию и сейчас решаем, кого из потенциальных "
    "спикеров пригласить на встречу.\n\n"
    "В списке — актёры, режиссёры, ведущие, эксперты и спикеры Российского "
    "общества «Знание». Но выбирать за участников не хотим: важно понять, ради "
    "кого вы действительно пришли бы.\n\n"
    "Можно отметить до 7 человек. Именно результаты голосования станут одним из "
    "главных ориентиров при формировании программы.\n\n"
    "Не нашёл своего кандидата? Его можно вписать в конце."
)


async def send_conference_survey_reminder(
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker,
) -> dict[str, int | str]:
    """One-off, idempotent reminder for approved users who have not completed survey 13."""
    async with session_factory() as session:
        survey = await session.get(AdminSurvey, SURVEY_ID)
        if survey is None:
            return {"status": "survey_missing", "eligible": 0, "sent": 0, "failed": 0, "duplicates": 0}
        if survey.status == "archived":
            return {"status": "survey_archived", "eligible": 0, "sent": 0, "failed": 0, "duplicates": 0}

        completed_response_exists = (
            select(AdminSurveyResponse.id)
            .where(
                AdminSurveyResponse.survey_id == SURVEY_ID,
                AdminSurveyResponse.user_id == User.id,
                AdminSurveyResponse.status == "completed",
            )
            .exists()
        )
        recipients = list(
            (
                await session.scalars(
                    select(User)
                    .where(
                        User.application_status == ApplicationStatus.APPROVED,
                        User.is_blocked.is_(False),
                        User.is_archived.is_(False),
                        ~completed_response_exists,
                    )
                    .order_by(User.id.asc())
                )
            ).all()
        )

    url = miniapp_path_url(settings.effective_miniapp_url, "surveys")
    markup = None
    if url:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔥 Выбрать спикеров",
                        web_app=WebAppInfo(url=url),
                    )
                ]
            ]
        )

    sent = 0
    failed = 0
    duplicates = 0
    for participant in recipients:
        result = await safe_send_once(
            bot,
            settings,
            participant.telegram_id,
            REMINDER_TEXT,
            delivery_key=f"conference-survey:{SURVEY_ID}:reminder:{DELIVERY_VERSION}:user:{participant.id}",
            notification_type="survey_reminder",
            reply_markup=markup,
        )
        if result.duplicate:
            duplicates += 1
        elif result.sent:
            sent += 1
        else:
            failed += 1

    summary = {
        "status": "done",
        "eligible": len(recipients),
        "sent": sent,
        "failed": failed,
        "duplicates": duplicates,
    }
    logger.info("Conference survey reminder finished: %s", summary)
    return summary
