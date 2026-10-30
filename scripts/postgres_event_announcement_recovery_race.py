"""Verify recovery cursor claims on disposable CI PostgreSQL; never contacts Telegram."""
import asyncio
import os
import uuid
from datetime import date, time

from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, User
from app.services.event_publication_service import (
    PUBLIC_STATUSES, RECOVERY_BATCH_SIZE, RECOVERY_CURSOR_KEY, _pending_announcement_ids,
)
from app.utils.constants import EventStatus


async def main():
    url = os.environ["DATABASE_URL"]
    parsed = make_url(url)
    if parsed.database != "era_test" or parsed.get_backend_name() != "postgresql":
        raise RuntimeError("Only isolated PostgreSQL era_test is allowed")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            user = User(telegram_id=40_000_000_000 + int(uuid.uuid4().hex[:7], 16), first_name="CI event recovery")
            session.add(user)
            await session.flush()
            events = [Event(title=f"CI recovery {i}", description="CI", event_date=date(2026, 11, 7),
                            event_time=time(18), location="CI", format="offline", created_by=user.id,
                            status=EventStatus.PUBLISHED) for i in range(8 * RECOVERY_BATCH_SIZE)]
            session.add_all(events)
            await session.flush()
            session.add_all([EventExperience(event_id=event.id, announcement_status="pending") for event in events])
            await session.execute(delete(AppSetting).where(AppSetting.key == RECOVERY_CURSOR_KEY))
            await session.commit()
            eligible = list((await session.scalars(select(EventExperience.event_id).join(
                Event, Event.id == EventExperience.event_id,
            ).where(EventExperience.announcement_status == "pending", Event.status.in_(PUBLIC_STATUSES))
                .order_by(EventExperience.event_id).limit(8 * RECOVERY_BATCH_SIZE))).all())

        pages = await asyncio.wait_for(asyncio.gather(*(_pending_announcement_ids(sessions) for _ in range(8))), 45)
        claimed = [event_id for page in pages for event_id in page]
        assert all(len(page) == RECOVERY_BATCH_SIZE for page in pages), pages
        assert len(claimed) == len(set(claimed)) == 8 * RECOVERY_BATCH_SIZE
        assert sorted(claimed) == eligible
        async with sessions() as session:
            cursor = await session.scalar(select(AppSetting.value).where(AppSetting.key == RECOVERY_CURSOR_KEY))
            assert int(cursor) == eligible[-1]
        # Verify the actual PostgreSQL/asyncpg comparison path, not only the
        # disposable SQLite unit test. A poisoned JSON AppSetting cursor must
        # never stall recovery or leak into an INTEGER bind.
        for damaged in (str(2**80), "9" * 5000, "-9223372036854775809", str(2_147_483_647)):
            async with sessions() as session:
                row = await session.scalar(select(AppSetting).where(AppSetting.key == RECOVERY_CURSOR_KEY))
                assert row is not None
                row.value = damaged
                await session.commit()
            page = await _pending_announcement_ids(sessions)
            assert page == eligible[:RECOVERY_BATCH_SIZE], (damaged[:32], page)
            async with sessions() as session:
                repaired = await session.scalar(select(AppSetting.value).where(AppSetting.key == RECOVERY_CURSOR_KEY))
                assert repaired == str(eligible[RECOVERY_BATCH_SIZE - 1]), repaired
        print("Event recovery PostgreSQL: poisoned/oversized cursor reset and asyncpg INTEGER bind verified")
        print("Event recovery PostgreSQL: 8 concurrent workers claim distinct bounded pages; no Telegram calls")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
