"""Create one Telegram forum topic per event. Keep uncertain creations for reconciliation."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.models import AppSetting
from app.services.notification_service import _session_factory


async def event_thread(bot, settings, event):
    chat_id = settings.general_chat_id
    if not chat_id or not str(chat_id).startswith("-100"):
        return None
    key = f"event-forum:{chat_id}:{event.id}"
    async with _session_factory(settings.database_url)() as session:
        record = await session.scalar(select(AppSetting).where(AppSetting.key == key))
        if record:
            return record.value.get("thread") if isinstance(record.value, dict) else None
        chat = await bot.get_chat(chat_id)
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        if not chat.is_forum or not (member.status == "creator" or getattr(member, "can_manage_topics", False)):
            return None
        record = AppSetting(key=key, value={"status": "creating"})
        session.add(record)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        topic = await bot.create_forum_topic(chat_id, name=event.title[:128])
        record.value = {"thread": topic.message_thread_id}
        await session.commit()
        return topic.message_thread_id
