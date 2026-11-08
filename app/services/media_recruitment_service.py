"""Owner-authorized media recruitment, delivered once through the existing ledger."""
import logging
import hashlib

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database.models import Broadcast, Direction
from app.services.general_topics_service import send_general_topic_once
from app.services.media_service import media_config

logger = logging.getLogger(__name__)
CAMPAIGN_KEY = "media-recruitment-20261026-v1"
TEXT = (
    "Медиа ЭРА ищет команду и руководителя\n\n"
    "Снимать интервью, ловить живые моменты, писать тексты, монтировать видео и придумывать, "
    "как рассказать о наших проектах так, чтобы их заметили.\n\n"
    "В медиаотделе можно пробовать разные роли, учиться на реальных задачах и собирать портфолио. "
    "Активные участники смогут претендовать на рекомендации ЭРА для профильных программ и медиафорумов.\n\n"
    "Отдельно ищем руководителя: человека, который соберёт команду, поможет распределять задачи "
    "и будет отвечать за выход материалов ЭРА и КСООРС.\n\n"
    "Хочешь создавать материалы — присоединяйся к команде. Готов взять ответственность за отдел — напиши Давиду."
)


def recruitment_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Присоединиться к команде", url="https://t.me/ERA_1bot?start=media_join")],
        [InlineKeyboardButton(text="Стать руководителем", url="https://t.me/davidbs2")],
        [InlineKeyboardButton(text="Чат медиа", url="https://t.me/+f03ksvhCMKc5NDBi")],
    ])


async def publish_media_recruitment(bot, settings, session_factory):
    # The shared general topic sender checks the forum and uses a durable receipt.
    # No private audience is inferred; this job publishes only the authorized notice.
    if getattr(settings, "feature_media", "OFF") != "ALL":
        return "media_disabled"
    if (not settings.general_chat_id or not settings.media_chat_id
            or settings.general_chat_id in {settings.media_chat_id, settings.leaders_chat_id}
            or not settings.era_chair_user_id):
        logger.warning("Media recruitment withheld: invalid chat/chair binding")
        return "not_configured"
    me = await bot.get_me()
    if (me.username or "").casefold() != "era_1bot":
        return "wrong_bot"
    async with session_factory() as session:
        direction = await session.scalar(select(Direction).where(Direction.name == "Медиа"))
        if direction is None or not (await media_config(session)).get("join_enabled", True):
            return "invitation_unavailable"
        # Do not advertise an occupied role as vacant or alter the current leader.
        if direction.leader_id is not None:
            return "leader_already_assigned"
    result = await send_general_topic_once(bot, settings, "notifications", TEXT,
        delivery_key=CAMPAIGN_KEY, reply_markup=recruitment_keyboard(), parse_mode=None)
    logger.info("Media recruitment delivery: status=%s duplicate=%s message_id=%s",
        result.status, result.duplicate, result.message_id)
    return result.status


# A separate, owner-authorized invitation to approved users in private messages.
# Distinct from the historical general-chat campaign above.
MEDIA_JOIN_DM_KEY = "media-club-invitation-20261108-v1"
MEDIA_JOIN_DM_TEXT = (
    "Хочешь быть частью команды, которая создаёт ЭРА?\n\n"
    "Открываем набор в медиаотдел! Здесь можно попробовать себя в съёмках, "
    "монтаже, дизайне, журналистике и ведении социальных сетей. Опыт не обязателен "
    "— главное, желание учиться и создавать.\n\n"
    "Впереди реальные проекты, выездные мероприятия, практика с партнёрами, "
    "сертификаты и возможность получить рекомендательное письмо за активную работу.\n\n"
    "Присоединяйся к команде медиа ЭРА:\n"
    "https://t.me/+f03ksvhCMKc5NDBi"
)


async def publish_media_join_direct_invitation(bot, settings, session_factory):
    """Once per campaign: the existing durable broadcast ledger owns all sends.

    Off by default. Never automatically renew the recipient snapshot on restart;
    any interrupted campaign is handled by resume_broadcasts instead.
    """
    if not getattr(settings, "media_join_dm_campaign_enabled", False):
        return "disabled"
    if settings.media_chat_url != "https://t.me/+f03ksvhCMKc5NDBi":
        logger.warning("Media invitation skipped: expected chat invitation changed")
        return "unexpected_chat"
    me = await bot.get_me()
    if (me.username or "").casefold() != "era_1bot":
        return "wrong_bot"
    from app.services.admin_broadcast_service import send_personal_broadcast

    # Hash is the same stable author/key pair used in the campaign service.
    campaign_hash = hashlib.sha256(f"None:{MEDIA_JOIN_DM_KEY}".encode()).hexdigest()
    async with session_factory() as session:
        existing = await session.scalar(select(Broadcast).where(
            Broadcast.audience_filter_json["campaign_key"].as_string() == campaign_hash
        ))
        if existing is not None:
            return f"existing:{existing.status}"
        result = await send_personal_broadcast(
            bot, session, audience="all", filter_value=None,
            text=MEDIA_JOIN_DM_TEXT, author_id=None, settings=settings,
            campaign_key=MEDIA_JOIN_DM_KEY,
        )
        logger.info("Media private recruitment: total=%s sent=%s failed=%s",
                    result.total, result.sent, result.failed)
        return "created"
