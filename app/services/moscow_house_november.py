"""Owner-approved November programme. Publish once in the ERA production forum."""
import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, text

from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, User
from app.services.event_publication_service import publish_event_announcement
from app.services.general_topics_service import ensure_topic, send_general_topic_once
from app.services.authorization_service import can_manage_events
from app.utils.constants import EventStatus
from app.utils.deep_links import telegram_event_miniapp_url

logger = logging.getLogger(__name__)
PLACE = "Дом Москвы в Ереване, ул. Аргишти, 7"
KEY = "november-2026-moscow-house"
EVENTS = (
    (23, 13, "Литература Победы. История, которая нас объединяет",
     "Семинар о русских и армянских писателях-фронтовиках. В программе открытый диалог и выставка архивных фотографий, фронтовых писем, дневников и стихов Победы."),
    (24, 19, "Тайны Серебряного века",
     "Творческий вечер Анны Эспарсы, культуролога и доктора исторических наук. Поэзия, живопись, театр, «Русские сезоны» Сергея Дягилева, стихи и романсы. В программе документальный фильм о Сергее Есенине."),
    (25, 17, "Наследие Достоевского в контексте мировой литературы",
     "Круглый стол к 205-летию со дня рождения Ф. М. Достоевского. С Анной Эспарсой обсудим философские идеи писателя, его влияние на мировую литературу и армянские переводы. Посмотрим фильм «Москва Федора Достоевского»."),
    (28, 10, "Образовательные мастер-классы для молодёжи",
     "Как создать сообщество, объединить людей и поддерживать их интерес? Спикер — Максим Артёмов, руководитель молодёжных проектов ЯНАО, лауреат премии Президента по поддержке талантливой молодёжи.\n\n10:15 — «Сообщество с нуля: собрать своих»\n11:45 — Кофе-брейк\n12:15 — «Почему люди остаются: нематериальная мотивация»\n14:00 — Завершение. Участникам предусмотрены сертификаты."),
)


async def publish_november_program(bot, settings, factory):
    if settings.dev_auth_enabled or settings.general_chat_id != -1002973371133:
        return
    if not date(2026, 11, 19) <= datetime.now(ZoneInfo("Asia/Yerevan")).date() < date(2026, 11, 23):
        return
    async with factory() as session:
        # Session-level lock spans independent commits and prevents two deployments
        # from launching the same public campaign. Bind a dedicated connection.
        async with session.bind.connect() as conn:
            if not await conn.scalar(text("SELECT pg_try_advisory_lock(2026111926205)")):
                return
            try:
                await _launch(bot, settings, session)
            finally:
                await conn.execute(text("SELECT pg_advisory_unlock(2026111926205)"))


async def _launch(bot, settings, session):
    receipt = await session.scalar(select(AppSetting).where(AppSetting.key == KEY))
    if receipt and receipt.value.get("complete"):
        return
    if await ensure_topic(bot, settings, "announcements", create_if_missing=False) != 26205:
        logger.warning("November programme needs the verified announcements topic")
        return
    chair = await session.get(User, settings.era_chair_user_id) if settings.era_chair_user_id else None
    if chair is None:
        chair = await session.scalar(select(User).where(
            or_(User.telegram_id.in_(settings.admin_ids), User.role == "admin"),
            or_(User.username.ilike("davidbs2"), (User.first_name.ilike("%Давид%") & User.last_name.ilike("%Багдасар%"))), User.is_blocked.is_(False), User.is_archived.is_(False),
        ))
    if not chair or not can_manage_events(chair, settings, chair.telegram_id):
        logger.warning("November programme needs the configured ERA chair")
        return
    username = (await bot.get_me()).username
    if (username or "").lower() != "era_1bot":
        return
    links = []
    ids = []
    topics = []
    for day, hour, title, description in EVENTS:
        event_date = date(2026, 11, day)
        marker = f"{KEY}:{day}"
        matches = list(await session.scalars(select(Event).where(Event.event_date == event_date,
            (Event.title == title) | (Event.additional_info == marker))))
        if len(matches) > 1 or (matches and matches[0].additional_info != marker):
            logger.warning("November programme found an existing event for day %s; reconcile before publication", day)
            return
        if not matches:
            event = Event(title=title, description=description, event_date=event_date, event_time=time(hour),
                location=PLACE, format="Офлайн", points_for_visit=0, status=EventStatus.REGISTRATION_OPEN,
                created_by=chair.id, approved_by=chair.id, additional_info=marker)
            session.add(event)
            await session.flush()
            exp = EventExperience(event_id=event.id, is_complete=True, creation_mode="quick", wizard_step=10,
                full_description=description, short_description=description, end_time=time(14) if day == 28 else None,
                issue_certificate=day == 28, broadcast_targets=["project_topic", "digest_only"], announcement_status="not_requested")
            session.add(exp)
            await session.commit()
        else:
            event = matches[0]
            exp = await session.get(EventExperience, event.id)
        if exp is None or event.status != EventStatus.REGISTRATION_OPEN:
            return
        if exp.announcement_status != "sent":
            if exp.announcement_status == "needs_attention" or not await publish_event_announcement(bot, settings, session, event, exp):
                await session.commit()
                return
            exp.announcement_status = "sent"
            await session.commit()
        links.append(f"{day} ноября · {hour}:00 — {title}\nРегистрация: {telegram_event_miniapp_url(username, event.id)}\nТема: {exp.chat_url}")
        ids.append(event.id)
        topics.append(exp.chat_url)
    message = "Четыре повода встретиться в Доме Москвы\n\n" + "\n\n".join(links)
    message += f"\n\n📍 {PLACE}\nДля участия выберите мероприятие и зарегистрируйтесь.\nОбщий чат ЭРА: {settings.general_chat_url}"
    result = await send_general_topic_once(bot, settings, "announcements", message,
        delivery_key=KEY, max_attempts=1)
    if result.sent:
        session.add(AppSetting(key=KEY, value={"complete": True, "events": ids, "message": result.message_id}))
        await session.commit()
        logger.info("November programme published events=%s topics=%s thread=26205 message=%s", ids, topics, result.message_id)
