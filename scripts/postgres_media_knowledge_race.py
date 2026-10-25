"""Shared catalogue races on disposable era_test only."""
import asyncio
import os
import uuid
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import Settings
from app.database.media_models import MediaLibraryItem
from app.database.models import AuditLog, User
from app.services import media_knowledge_service as knowledge

async def main():
    url = os.environ["DATABASE_URL"]
    parsed = make_url(url)
    if parsed.database != "era_test" or parsed.get_backend_name() != "postgresql":
        raise RuntimeError("Only isolated PostgreSQL era_test is allowed")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            chair = User(telegram_id=70_000_000_000 + int(uuid.uuid4().hex[:7], 16), first_name="CI knowledge", application_status="approved")
            session.add(chair)
            await session.commit()
            ident = chair.id
        settings = Settings(bot_token="0000000000:CITESTTOKEN", era_chair_user_id=ident)
        key = str(uuid.uuid4())
        async def create():
            async with sessions() as session:
                item = await knowledge.create_item(session, await session.get(User, ident), settings,
                    {"kind": "text", "category": "texts", "title": "CI knowledge", "description": "Disposable instruction"}, key)
                await session.commit()
                return item.id
        ids = await asyncio.wait_for(asyncio.gather(*(create() for _ in range(8))), 45)
        assert len(set(ids)) == 1
        item_id = ids[0]
        async with sessions() as session:
            revision = await knowledge.revision(session, item_id)
        async def change():
            async with sessions() as session:
                try:
                    await knowledge.update_item(session, await session.get(User, ident), settings, item_id, {"pinned": True}, revision)
                    await session.commit()
                    return True
                except ValueError as error:
                    assert str(error) == "Материал уже изменён. Обновите базу знаний"
                    await session.rollback()
                    return False
        assert sum(await asyncio.wait_for(asyncio.gather(*(change() for _ in range(8))), 45)) == 1
        async with sessions() as session:
            assert await session.scalar(select(func.count(MediaLibraryItem.id)).where(MediaLibraryItem.id == item_id)) == 1
            for action in knowledge.ACTIONS:
                assert await session.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == action, AuditLog.entity_id == item_id)) == 1
        print("Media knowledge PostgreSQL: 8 creates -> 1 item, 8 stale edits -> 1 accepted, one audit each")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
