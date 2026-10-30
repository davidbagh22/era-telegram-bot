"""Calendar create/revision races on disposable CI PostgreSQL only."""
import asyncio
import os
import uuid

from sqlalchemy import delete, func, null, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.media_models import MediaContentItem
from app.database.models import AuditLog, Department, Direction, PermissionGrant, User, UserDirection
from app.services import media_scope_service as scopes
from app.services.media_service import decide_media_application
from app.services.media_workspace_service import calendar, create_entry, update_entry


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
        # Serialize grants and membership removal with calendar writes on the same Direction row.
        async with sessions() as session:
            direction = await session.scalar(select(Direction).where(Direction.name == "Медиа"))
            if direction is None:
                department = Department(name="CI calendar scopes")
                session.add(department)
                await session.flush()
                direction = Direction(name="Медиа", department_id=department.id)
                session.add(direction)
                await session.flush()
            editor = User(telegram_id=60_000_000_000 + int(uuid.uuid4().hex[:7], 16), first_name="CI editor", application_status="approved")
            session.add(editor)
            await session.flush()
            session.add(UserDirection(user_id=editor.id, direction_id=direction.id, status="approved"))
            await session.commit()
            editor_id, direction_id = editor.id, direction.id
        async def grant():
            async with sessions() as session:
                state = await scopes.set_editor(session, await session.get(User, chair_id), settings, "era", editor_id, True, 0)
                await session.commit()
                return state
        states = await asyncio.wait_for(asyncio.gather(*(grant() for _ in range(8))), 45)
        assert len({state["revision"] for state in states}) == 1
        async with sessions() as session:
            assert await session.scalar(select(func.count(PermissionGrant.id)).where(
                PermissionGrant.user_id == editor_id, PermissionGrant.is_active.is_(True))) == 1
            assert await session.scalar(select(func.count(AuditLog.id)).where(
                AuditLog.action == scopes.ACTION, AuditLog.entity_id == direction_id)) == 1
        async def remove():
            async with sessions() as session:
                await decide_media_application(session, editor_id, "revoke", actor=await session.get(User, chair_id), settings=settings)
                await session.commit()
        async def editor_write():
            async with sessions() as session:
                try:
                    await create_entry(session, await session.get(User, editor_id), settings, "era",
                        {"title": "CI revoke race", "platform": "telegram"}, str(uuid.uuid4()))
                    await session.commit()
                except PermissionError:
                    await session.rollback()
        await asyncio.wait_for(asyncio.gather(remove(), editor_write()), 45)
        async with sessions() as session:
            editor = await session.get(User, editor_id)
            assert not await scopes.can_edit_calendar(session, editor, settings, "era")
            await decide_media_application(session, editor_id, "approve", actor=await session.get(User, chair_id), settings=settings)
            assert not await scopes.can_edit_calendar(session, editor, settings, "era")
            await session.commit()
        # Isolated PostgreSQL proof for #554: invalid JSON must be filtered
        # in SQL before LIMIT 100, not after it. This runs ONLY against era_test.
        token = uuid.uuid4().hex
        prefix = f"ci-json-{token}-"
        async with sessions() as session:
            metadata = [
                {"media_area": "era"},
                {"workspace_revision": 0},
                {"media_area": "ksoors"},
                null(),  # actual SQL NULL, retained for historical ERA rows
                {"media_area": None},  # explicit JSON null is not a valid area
            ] + [["malformed"]] * 125
            items = [MediaContentItem(
                source_kind="media_workspace", source_key=f"{prefix}{index}",
                kind="text", title=f"CI JSON {index}", status="planned",
                metadata_json=value,
            ) for index, value in enumerate(metadata)]
            try:
                session.add_all(items)
                await session.flush()
                era_ids = [items[index].id for index in (0, 1, 3)]
                ksoors_id = items[2].id
                await session.commit()
                era_page = await calendar(session, "era")
                assert [row["id"] for row in era_page[:3]] == sorted(era_ids, reverse=True), era_page[:5]
                assert all(row["area"] == "era" for row in era_page)
                assert [row["id"] for row in (await calendar(session, "era", before_id=era_ids[2]))[:2]] == sorted(era_ids[:2], reverse=True)
                ksoors_page = await calendar(session, "ksoors")
                assert ksoors_page[0]["id"] == ksoors_id, ksoors_page[:3]
                assert all(row["area"] == "ksoors" for row in ksoors_page)
            finally:
                await session.rollback()
                await session.execute(delete(MediaContentItem).where(MediaContentItem.source_key.like(f"{prefix}%")))
                await session.commit()
        print("Media calendar PostgreSQL: malformed JSON excluded before LIMIT, ERA/KSOORS scoped pages and cursor verified")
        print("Calendar scopes PostgreSQL: 8 grants -> 1 audit; revoke/write serialized; rejoin never restores editing")
        print("Media calendar PostgreSQL: 8 creates -> 1 item, 8 updates -> 1 revision, one audit per action")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
