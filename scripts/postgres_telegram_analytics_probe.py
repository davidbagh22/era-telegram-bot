"""Run only against CI's disposable PostgreSQL, never production."""
import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace

from aiogram.types import Chat, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.telegram_analytics import TelegramMessageFact
from app.services.telegram_analytics_service import observe_message


async def main():
    url = os.environ['DATABASE_URL']
    if '@127.0.0.1:5432/era_test' not in url:
        raise RuntimeError('Disposable local CI database required')
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine)
    now = datetime.now(timezone.utc)
    message = Message(message_id=21, chat=Chat(id=-999000111, type='channel'), date=now, text='CI fixture')

    async def observe():
        async with factory() as session:
            await observe_message(session, message, kind='channel')
            await session.commit()

    await asyncio.gather(*(observe() for _ in range(30)))
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(TelegramMessageFact).where(TelegramMessageFact.chat_id == message.chat.id))
        assert count == 1, count
        from app.services.telegram_analytics_service import telegram_snapshot, report_window
        settings = SimpleNamespace(era_channel_id=message.chat.id, general_chat_id=None, timezone='Asia/Yerevan')
        start, end = report_window(days=7)
        snapshot = await telegram_snapshot(session, settings, start=start, end=end)
        assert snapshot['sources'][0]['total_observed'] == 1
        assert snapshot['sources'][0]['value'] is None  # No invented permission/coverage proof.
    await engine.dispose()
    print('Telegram duplicate delivery: 30 concurrent observations -> 1 fact; coverage remains unverified')


if __name__ == '__main__':
    asyncio.run(main())
