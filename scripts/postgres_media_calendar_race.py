"""Calendar create/revision races on disposable CI PostgreSQL only."""
import asyncio
import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.media_models import MediaContentItem
from app.database.models import AuditLog, User
from app.services.media_workspace_service import create_entry, update_entry


async def main():
    url = os.environ["DATABASE_URL"]
    if make_url(url).database != "era_test" or make_url(url).get_backend_name() != "postgresql":
        raise RuntimeError("Only isolated PostgreSQL era_test is allowed")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            chair = User(telegram_id=50_000_000_000 + int(uuid.uuid4().hex[:7], 16), first_name="CI calendar", application_status="approved")
            session.add(chair)
            await session.commit()
            chair_id = chair.id
        settings = Settings(bot_token="0000000000:CITESTTOKEN", era_chair_user_id=chair_id)
        key = str(uuid.uuid4())
        async def create():
            async with sessions() as session:
                item = await create_entry(session, await session.get(User, chair_id), settings, "ksoors",
                    {"title": "Изолированный календарь", "platform": "telegram"}, key)
                await session.commit()
                return item.id
        ids = await asyncio.wait_for(asyncio.gather(*(create() for _ in range(8))), 45)
        assert len(set(ids)) == 1, ids
        item_id = ids[0]
        async def update():
            async with sessions() as session:
                try:
                    await update_entry(session, await session.get(User, chair_id), settings, "ksoors", item_id,
                        {"status": "review"}, 0)
                    await session.commit()
                    return True
                except ValueError as error:
                    assert str(error) == "Материал уже изменён. Обновите календарь", str(error)
                    await session.rollback()
                    return False
        assert sum(await asyncio.wait_for(asyncio.gather(*(update() for _ in range(8))), 45)) == 1
        async with sessions() as session:
            assert await session.scalar(select(func.count(MediaContentItem.id)).where(
                MediaContentItem.source_key == f"workspace:{chair_id}:{key}")) == 1
            for action in ("media.calendar_created", "media.calendar_updated"):
                assert await session.scalar(select(func.count(AuditLog.id)).where(
                    AuditLog.action == action, AuditLog.entity_id == item_id)) == 1
        print("Media calendar PostgreSQL: 8 creates -> 1 item, 8 updates -> 1 revision, one audit per action")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
