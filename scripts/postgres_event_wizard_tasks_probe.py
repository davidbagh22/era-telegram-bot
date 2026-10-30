"""Prove malformed event wizard JSON cannot block healthy tasks on disposable PG.

No Telegram API, no production database, no participant registration or awards.
"""
import asyncio
import os
import uuid
from datetime import date, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.event_experience import EventExperience
from app.database.models import Event, EventActivity, User
from app.services.event_wizard_sync_service import sync_event_wizard_tasks
from app.utils.constants import EventStatus


async def main():
    url = os.environ["DATABASE_URL"]
    parsed = make_url(url)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.database != "era_test"
        or parsed.username != "era_test"
        or parsed.host not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise RuntimeError("Only disposable PostgreSQL era_test is allowed")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            creator = User(
                telegram_id=60_000_000_000 + int(uuid.uuid4().hex[:8], 16),
                first_name="CI wizard recovery",
            )
            session.add(creator)
            await session.flush()
            ids = []
            cases = [
                ([{"title": "Bad points", "points": "not-an-integer"}], []),
                ([{"title": "Bad ids", "points": 4}], ["not-an-id"]),
                ({}, []),  # falsey non-list tasks must not mean "delete all"
                ([{"title": "Would duplicate", "points": 7}], {}),
                ([{"title": "Good", "points": 7}], []),
            ]
            for tasks, old_ids in cases:
                event = Event(
                    title="CI wizard task recovery",
                    description="No Telegram delivery",
                    event_date=date.today() + timedelta(days=3),
                    event_time=time(18),
                    location="CI",
                    format="offline",
                    created_by=creator.id,
                    status=EventStatus.PUBLISHED,
                )
                session.add(event)
                await session.flush()
                ids.append(event.id)
                session.add(EventExperience(
                    event_id=event.id, is_complete=True,
                    participant_tasks=tasks,
                    participant_task_activity_ids=old_ids,
                ))
            await session.commit()

        async with sessions() as session:
            await sync_event_wizard_tasks(session)
            for bad_id in ids[:-1]:
                assert await session.scalar(select(func.count(EventActivity.id)).where(
                    EventActivity.event_id == bad_id
                )) == 0
            good = list((await session.scalars(select(EventActivity).where(
                EventActivity.event_id == ids[-1]
            ))).all())
            assert len(good) == 1 and good[0].title == "Good" and good[0].points == 7
            saved_id = good[0].id
            exp = await session.get(EventExperience, ids[-1])
            assert exp.participant_task_activity_ids == [saved_id]

        async with sessions() as session:
            await sync_event_wizard_tasks(session)
            assert await session.scalar(select(func.count(EventActivity.id)).where(
                EventActivity.event_id == ids[-1]
            )) == 1
            for bad_id in ids[:-1]:
                assert await session.scalar(select(func.count(EventActivity.id)).where(
                    EventActivity.event_id == bad_id
                )) == 0
        # Force both scheduler sessions to finish their initial unlocked scan
        # before either may materialise a new task. Without the refreshed
        # EventExperience FOR UPDATE lock, both can insert an EventActivity.
        async with sessions() as session:
            race_event = Event(
                title="CI concurrent wizard materialisation",
                description="Disposable PostgreSQL only",
                event_date=date.today() + timedelta(days=3),
                event_time=time(18),
                location="CI",
                format="offline",
                created_by=creator.id,
                status=EventStatus.PUBLISHED,
            )
            session.add(race_event)
            await session.flush()
            race_event_id = race_event.id
            session.add(EventExperience(
                event_id=race_event_id,
                is_complete=True,
                participant_tasks=[{"title": "Only once", "points": 5}],
                participant_task_activity_ids=[],
            ))
            await session.commit()

        both_scanned = asyncio.Event()
        arrivals = 0

        async def concurrent_worker():
            nonlocal arrivals
            async with sessions() as session:
                original_execute = session.execute
                first_scan = True

                async def synchronize_initial_scan(statement, *args, **kwargs):
                    nonlocal arrivals, first_scan
                    result = await original_execute(statement, *args, **kwargs)
                    if first_scan:
                        first_scan = False
                        arrivals += 1
                        if arrivals == 2:
                            both_scanned.set()
                        await asyncio.wait_for(both_scanned.wait(), timeout=15)
                    return result

                session.execute = synchronize_initial_scan
                return await sync_event_wizard_tasks(session)

        await asyncio.wait_for(
            asyncio.gather(concurrent_worker(), concurrent_worker()),
            timeout=35,
        )
        assert arrivals == 2, "Both sessions must read before the row lock"
        async with sessions() as session:
            activities = list((await session.scalars(
                select(EventActivity).where(EventActivity.event_id == race_event_id)
            )).all())
            assert len(activities) == 1, (
                "Concurrent scheduler workers created duplicate participant tasks"
            )
            assert activities[0].title == "Only once"
            experience = await session.get(EventExperience, race_event_id)
            assert experience.participant_task_activity_ids == [activities[0].id]

        print("Wizard PostgreSQL: two concurrent stale scans created one task")
        print("Wizard PostgreSQL: malformed rows skipped; healthy task created once")
        print("Wizard PostgreSQL: second pass idempotent; no Telegram or point awards")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
