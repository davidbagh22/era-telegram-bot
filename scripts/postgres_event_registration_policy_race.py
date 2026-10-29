"""Prove registration policy and last-seat locking on disposable CI PostgreSQL.

This probe does not contact Telegram. It refuses remote and non-CI databases.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.services.event_service import register_for_event
from app.utils.constants import EventStatus, RegistrationStatus


async def main() -> None:
    url = os.environ["DATABASE_URL"]
    parsed = make_url(url)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.database != "era_test"
        or parsed.username != "era_test"
        or parsed.host not in {"127.0.0.1", "localhost"}
    ):
        raise RuntimeError("Only isolated localhost PostgreSQL era_test is allowed")
    engine = create_async_engine(url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    nonce = int(uuid.uuid4().hex[:8], 16)
    try:
        async with sessions() as session:
            users = [
                User(telegram_id=80_000_000_000 + nonce * 10 + i, first_name="CI policy")
                for i in range(4)
            ]
            session.add_all(users)
            await session.flush()
            event = Event(
                title="CI policy lock race",
                description="Disposable PostgreSQL concurrency fixture",
                event_date=date.today() + timedelta(days=2),
                event_time=time(18, 0),
                location="CI",
                format="offline",
                created_by=users[0].id,
                status=EventStatus.REGISTRATION_OPEN,
                participant_limit=1,
            )
            session.add(event)
            await session.flush()
            session.add(EventExperience(
                event_id=event.id,
                registration_required=True,
                waitlist_enabled=True,
            ))
            await session.commit()
            event_id = event.id
            user_ids = [u.id for u in users]

        loaded = asyncio.Event()
        admin_locked = asyncio.Event()
        register_started = asyncio.Event()

        async def stale_registration() -> str | None:
            async with sessions() as session:
                stale_event = await session.get(Event, event_id)
                stale_policy = await session.get(EventExperience, event_id)
                assert stale_event is not None and stale_policy is not None
                assert stale_policy.registration_required
                loaded.set()
                await admin_locked.wait()
                register_started.set()
                registration, error = await register_for_event(
                    session, stale_event, user_ids[1], waitlist_enabled=True,
                )
                assert registration is None
                await session.rollback()
                return error

        async def admin_disables_registration() -> None:
            await loaded.wait()
            async with sessions() as session:
                locked_event = await session.scalar(
                    select(Event).where(Event.id == event_id).with_for_update()
                )
                policy = await session.scalar(
                    select(EventExperience)
                    .where(EventExperience.event_id == event_id)
                    .with_for_update()
                )
                assert locked_event is not None and policy is not None
                policy.registration_required = False
                await session.flush()
                admin_locked.set()
                await register_started.wait()
                await asyncio.sleep(0.15)
                await session.commit()

        error, _ = await asyncio.wait_for(
            asyncio.gather(stale_registration(), admin_disables_registration()),
            timeout=40,
        )
        assert error == "registration_not_required", error

        async with sessions() as session:
            count = await session.scalar(
                select(func.count(EventRegistration.id))
                .where(EventRegistration.event_id == event_id)
            )
            assert count == 0, count
            policy = await session.get(EventExperience, event_id)
            assert policy is not None
            policy.registration_required = True
            policy.registration_close_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.commit()

        async with sessions() as session:
            event = await session.get(Event, event_id)
            assert event is not None
            registration, error = await register_for_event(
                session, event, user_ids[1], waitlist_enabled=True,
            )
            assert registration is None and error == "closed", error
            await session.rollback()

        async with sessions() as session:
            policy = await session.get(EventExperience, event_id)
            assert policy is not None
            policy.registration_close_at = None
            policy.waitlist_enabled = False
            await session.commit()

        # Both requests see an initially free last seat; the event-row lock
        # must permit only one registration and reject the other as full.
        barrier = asyncio.Barrier(2)

        async def register_last_seat(user_id: int) -> str:
            async with sessions() as session:
                event = await session.get(Event, event_id)
                assert event is not None
                await barrier.wait()
                registration, error = await register_for_event(
                    session, event, user_id, waitlist_enabled=True,
                )
                await session.commit()
                if error is not None:
                    assert registration is None
                    return error
                assert registration is not None
                return registration.status

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                register_last_seat(user_ids[2]),
                register_last_seat(user_ids[3]),
            ),
            timeout=40,
        )
        assert sorted(outcomes) == sorted([RegistrationStatus.REGISTERED, "full"]), outcomes
        async with sessions() as session:
            count = await session.scalar(
                select(func.count(EventRegistration.id)).where(
                    EventRegistration.event_id == event_id,
                    EventRegistration.status == RegistrationStatus.REGISTERED,
                )
            )
            assert count == 1, count
        print("PostgreSQL event policy: stale caller denied after admin edit; deadline enforced; last seat allocated once")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
