from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.database.models import User
from app.services.notification_service import safe_send_once
from app.utils.constants import ApplicationStatus
from app.utils.deep_links import telegram_miniapp_start_url

router = APIRouter(prefix="/ops/vector-20260909")

_RUN_TOKEN = "UV-r0sIsbWJE4KzaA-OuZ5B3kYc3CDtL"
_CAMPAIGN_KEY = "vector-20260909"

PERSONAL_TEXT = """🧭 А что твои ответы могут рассказать о тебе?

В ЭРА обновился «Мой вектор».

Пройди короткий тест и получи персональный разбор: твои сильные стороны, текущее состояние, точки внимания и возможный следующий шаг.

А дальше ЭРА сможет показывать тебе проекты, роли, обучение и возможности, которые больше подходят именно под твой вектор.

Это не оценка и не рейтинг. Это возможность чуть лучше понять себя."""

CHANNEL_TEXT = """Иногда полезно не спрашивать «что делать дальше?», а сначала понять — где ты сейчас.

В «Моём векторе» появился персональный анализ.

Ты проходишь короткий тест, а система собирает ответы в одну картину и показывает:
— твои сильные стороны;
— текущее состояние;
— что требует внимания;
— возможное направление дальнейшего роста.

Но на этом всё не заканчивается.

Постепенно рядом с твоим результатом будут появляться возможности ЭРА именно под твой вектор: проекты, новые роли, мероприятия, обучение и другие форматы развития.

Не рейтинг. Не правильные и неправильные ответы.

Просто возможность узнать о себе чуть больше."""


def _count_result(result, counters: dict[str, int]) -> None:
    if result.duplicate:
        counters["duplicates"] += 1
    elif result.sent:
        counters["sent"] += 1
    else:
        counters["failed"] += 1


@router.get(f"/{_RUN_TOKEN}", include_in_schema=False)
async def run_vector_campaign(request: Request) -> dict[str, object]:
    bot = getattr(request.app.state, "bot", None)
    settings = getattr(request.app.state, "settings", None)
    session_factory = getattr(request.app.state, "session_factory", None)
    if bot is None or settings is None or session_factory is None:
        raise HTTPException(status_code=503, detail="service_not_ready")

    me = await bot.get_me()
    button_url = telegram_miniapp_start_url(me.username or settings.bot_username, "development")
    if not button_url:
        raise HTTPException(status_code=503, detail="bot_username_unavailable")

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧭 Узнать свой вектор", url=button_url)]
        ]
    )

    async with session_factory() as session:
        recipients = list(
            (
                await session.scalars(
                    select(User)
                    .where(
                        User.application_status == ApplicationStatus.APPROVED,
                        User.is_blocked.is_(False),
                        User.is_archived.is_(False),
                    )
                    .order_by(User.id)
                )
            ).all()
        )

    counters = {"sent": 0, "failed": 0, "duplicates": 0}
    for target in recipients:
        result = await safe_send_once(
            bot,
            settings,
            int(target.telegram_id),
            PERSONAL_TEXT,
            delivery_key=f"campaign:{_CAMPAIGN_KEY}:user:{int(target.telegram_id)}",
            notification_type="vector_campaign",
            reply_markup=markup,
        )
        _count_result(result, counters)

    general_status = "not_configured"
    if settings.general_chat_id:
        result = await safe_send_once(
            bot,
            settings,
            int(settings.general_chat_id),
            PERSONAL_TEXT,
            delivery_key=f"campaign:{_CAMPAIGN_KEY}:general",
            notification_type="vector_campaign",
            reply_markup=markup,
        )
        general_status = "duplicate" if result.duplicate else result.status

    channel_status = "not_configured"
    channel_ref = settings.era_channel_id or (
        f"@{settings.era_channel_username.lstrip('@')}"
        if settings.era_channel_username
        else ""
    )
    if channel_ref:
        try:
            channel = await bot.get_chat(channel_ref)
            result = await safe_send_once(
                bot,
                settings,
                int(channel.id),
                CHANNEL_TEXT,
                delivery_key=f"campaign:{_CAMPAIGN_KEY}:channel",
                notification_type="vector_campaign",
                reply_markup=markup,
            )
            channel_status = "duplicate" if result.duplicate else result.status
        except Exception:
            channel_status = "delivery_failed"

    return {
        "ok": True,
        "recipients": len(recipients),
        "personal": counters,
        "general": general_status,
        "channel": channel_status,
    }
