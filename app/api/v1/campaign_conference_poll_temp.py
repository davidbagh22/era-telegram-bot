from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import APIRouter, HTTPException, Request

from app.services import survey_admin_service
from app.services.notification_service import safe_send_once
from app.services.survey_service import CONFERENCE_SURVEY_MARKER, CONFERENCE_SURVEY_TITLE
from app.utils.deep_links import telegram_miniapp_start_url

router = APIRouter(prefix="/ops/conference-speaker-poll-20260909")

_RUN_TOKEN = "f4c8c1f7d54047aab0f4c1f47a838c62"
_DELIVERY_KEY = "campaign:conference-speakers-20260909:general:v1"

CHAT_TEXT = """🔥 Кого ты реально хочешь услышать вживую?

Мы собираем программу молодёжной конференции ЭРА — и хотим решить её вместе с вами.

Внутри один список потенциальных спикеров. Выбери до 7 человек — тех, ради встречи с кем ты действительно пришёл бы.

Не нашёл нужного человека? В конце можно вписать своего кандидата.

Именно по результатам этого голосования будем собирать программу конференции."""


async def run_conference_speaker_poll_once(bot, settings, session_factory) -> dict[str, object]:
    if not settings.general_chat_id:
        raise RuntimeError("general_chat_not_bound")

    async with session_factory() as session:
        survey = await survey_admin_service.create_survey(
            session,
            title=CONFERENCE_SURVEY_TITLE,
            description=None,
            questions=[CONFERENCE_SURVEY_MARKER],
            created_by_id=None,
        )
        await session.commit()
        survey_id = int(survey.id)

    me = await bot.get_me()
    button_url = telegram_miniapp_start_url(me.username or settings.bot_username, "surveys")
    if not button_url:
        raise RuntimeError("miniapp_link_unavailable")

    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Выбрать спикеров", url=button_url)]]
    )
    result = await safe_send_once(
        bot,
        settings,
        int(settings.general_chat_id),
        CHAT_TEXT,
        delivery_key=_DELIVERY_KEY,
        notification_type="conference_speaker_poll",
        reply_markup=markup,
    )
    return {
        "survey_id": survey_id,
        "status": result.status,
        "sent": result.sent,
        "duplicate": result.duplicate,
        "error_code": result.error_code,
    }


@router.get(f"/{_RUN_TOKEN}", include_in_schema=False)
async def run_conference_poll(request: Request) -> dict[str, object]:
    bot = getattr(request.app.state, "bot", None)
    settings = getattr(request.app.state, "settings", None)
    session_factory = getattr(request.app.state, "session_factory", None)
    if bot is None or settings is None or session_factory is None:
        raise HTTPException(status_code=503, detail="service_not_ready")
    try:
        return await run_conference_speaker_poll_once(bot, settings, session_factory)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
