#!/usr/bin/env python3
"""Prove event capacity and waitlist promotions under PostgreSQL concurrency."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import Event, EventRegistration, User
from app.services.event_service import promote_waitlist, register_for_event
from app.utils.constants import EventStatus, RegistrationStatus


async def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql" or url.database != "era_test":
        raise RuntimeError("Only isolated PostgreSQL era_test is allowed")

    engine = create_async_engine(database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    nonce = uuid.uuid4().hex[:12]
    telegram_base = 8_100_000_000 + int(nonce[:7], 16)
    try:
        async with sessions() as session:
            creator = User(
                telegram_id=telegram_base,
                first_name="CI waitlist creator",
                application_status="approved",
            )
            participants = [
                User(
                    telegram_id=telegram_base + index + 1,
                    first_name=f"CI waitlist {index}",
                    application_status="approved",
                )
                for index in range(8)
            ]
            session.add_all([creator, *participants])
            await session.flush()
            event = Event(
                title=f"CI capacity {nonce}",
                description="Disposable PostgreSQL concurrency fixture",
                event_date=date.today() + timedelta(days=3),
                event_time=time(18),
                location="CI only",
                format="Offline",
                participant_limit=1,
                created_by=creator.id,
                status=EventStatus.REGISTRATION_OPEN,
            )
            session.add(event)
            await session.commit()
            event_id = event.id
            participant_ids = [participant.id for participant in participants]

        async def register(user_id: int) -> str:
            async with sessions() as session:
                current_event = await session.get(Event, event_id)
                registration, error = await register_for_event(
                    session, current_event, user_id, waitlist_enabled=True
                )
                await session.commit()
                if error is not None or registration is None:
                    raise AssertionError(f"registration failed: {error}")
                return registration.status

        statuses = await asyncio.wait_for(
            asyncio.gather(*(register(user_id) for user_id in participant_ids)),
            timeout=45,
        )
        assert statuses.count(RegistrationStatus.REGISTERED) == 1, statuses
        assert statuses.count(RegistrationStatus.WAITLIST) == 7, statuses

        async def replay(user_id: int) -> None:
            async with sessions() as session:
                current_event = await session.get(Event, event_id)
                registration, error = await register_for_event(
                    session, current_event, user_id, waitlist_enabled=True
                )
                assert registration is None and error == "already", (registration, error)
                await session.rollback()

        await asyncio.wait_for(
            asyncio.gather(*(replay(user_id) for user_id in participant_ids)),
            timeout=45,
        )

        async with sessions() as session:
            registered = await session.scalar(
                select(EventRegistration).where(
                    EventRegistration.event_id == event_id,
                    EventRegistration.status == RegistrationStatus.REGISTERED,
                )
            )
            assert registered is not None
            registered.status = RegistrationStatus.CANCELLED
            await session.commit()

        barrier = asyncio.Barrier(len(participant_ids))

        async def promote() -> int | None:
            async with sessions() as session:
                current_event = await session.get(Event, event_id)
                await barrier.wait()
                registration = await promote_waitlist(session, current_event)
                await session.commit()
                return registration.id if registration is not None else None

        promotions = await asyncio.wait_for(
            asyncio.gather(*(promote() for _ in participant_ids)),
            timeout=45,
        )
        assert sum(registration_id is not None for registration_id in promotions) == 1, promotions

        async with sessions() as session:
            registered_count = int(
                await session.scalar(
                    select(func.count(EventRegistration.id)).where(
                        EventRegistration.event_id == event_id,
                        EventRegistration.status == RegistrationStatus.REGISTERED,
                    )
                )
                or 0
            )
            waitlist_count = int(
                await session.scalar(
                    select(func.count(EventRegistration.id)).where(
                        EventRegistration.event_id == event_id,
                        EventRegistration.status == RegistrationStatus.WAITLIST,
                    )
                )
                or 0
            )
            registration_count = int(
                await session.scalar(
                    select(func.count(EventRegistration.id)).where(
                        EventRegistration.event_id == event_id
                    )
                )
                or 0
            )

        assert registered_count == 1, registered_count
        assert waitlist_count == 6, waitlist_count
        assert registration_count == 8, registration_count
        print("PostgreSQL event capacity/waitlist concurrency verification passed")
        print("registrations=8 capacity=1 registered=1 waitlist=7 duplicate_replays=8 promotions=1")
        print("after_release registered=1 waitlist=6 total_rows=8")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
