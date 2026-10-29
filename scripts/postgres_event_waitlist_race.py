"""Exercise waitlist cancellation and registration races on disposable CI PostgreSQL.

No Telegram API calls. Refuse every database except the isolated era_test
PostgreSQL service supplied by the GitHub Actions postgres-migration job.
"""
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
                User(telegram_id=70_000_000_000 + nonce * 10 + index, first_name="CI waitlist")
                for index in range(7)
            ]
            session.add_all(users)
            await session.flush()
            event = Event(
                title="CI waitlist race",
                description="Disposable PostgreSQL concurrency fixture",
                event_date=date.today() + timedelta(days=2),
                event_time=time(18, 0),
                location="CI",
                format="offline",
                created_by=users[0].id,
                status=EventStatus.REGISTRATION_OPEN,
                participant_limit=2,
            )
            session.add(event)
            await session.flush()
            session.add_all([
                EventRegistration(
                    event_id=event.id, user_id=users[index].id,
                    status=(
                        RegistrationStatus.REGISTERED if index in (1, 2)
                        else RegistrationStatus.WAITLIST
                    ),
                )
                for index in (1, 2, 3, 4, 5)
            ])
            await session.commit()
            event_id = event.id
            cancellation_user_ids = (users[1].id, users[2].id)
            direct_user_id = users[6].id

        # Both transactions have read their own registration before racing.
        # The event row lock must serialize their capacity checks and promote
        # exactly two different waitlisted participants into the freed seats.
        barrier = asyncio.Barrier(2)

        async def cancel_and_promote(user_id: int) -> int | None:
            async with sessions() as session:
                event = await session.get(Event, event_id)
                registration = await session.scalar(
                    select(EventRegistration).where(
                        EventRegistration.event_id == event_id,
                        EventRegistration.user_id == user_id,
                    )
                )
                assert event is not None and registration is not None
                await barrier.wait()
                registration.status = RegistrationStatus.CANCELLED
                promoted = await promote_waitlist(session, event)
                await session.commit()
                return promoted.user_id if promoted is not None else None

        promoted = await asyncio.wait_for(
            asyncio.gather(*(cancel_and_promote(uid) for uid in cancellation_user_ids)),
            timeout=45,
        )
        assert len(set(promoted)) == 2 and None not in promoted, promoted

        async def counts() -> dict[str, int]:
            async with sessions() as session:
                rows = await session.execute(
                    select(EventRegistration.status, func.count())
                    .where(EventRegistration.event_id == event_id)
                    .group_by(EventRegistration.status)
                )
                return dict(rows.all())

        first = await counts()
        assert first.get(RegistrationStatus.REGISTERED, 0) == 2, first
        assert first.get(RegistrationStatus.WAITLIST, 0) == 1, first
        assert first.get(RegistrationStatus.CANCELLED, 0) == 2, first

        # Free one seat and race a direct new registration against a waitlist
        # promotion. At most one may consume the last place.
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

        second_barrier = asyncio.Barrier(2)

        async def promote() -> int | None:
            async with sessions() as session:
                event = await session.get(Event, event_id)
                assert event is not None
                await second_barrier.wait()
                promoted = await promote_waitlist(session, event)
                await session.commit()
                return promoted.user_id if promoted else None

        async def register() -> str:
            async with sessions() as session:
                event = await session.get(Event, event_id)
                assert event is not None
                await second_barrier.wait()
                registration, error = await register_for_event(
                    session, event, direct_user_id, waitlist_enabled=True,
                )
                assert error is None and registration is not None, error
                await session.commit()
                return registration.status

        await asyncio.wait_for(asyncio.gather(promote(), register()), timeout=45)
        final = await counts()
        assert final.get(RegistrationStatus.REGISTERED, 0) == 2, final
        assert final.get(RegistrationStatus.CANCELLED, 0) == 3, final
        print("PostgreSQL event waitlist: 2 simultaneous cancellations promote 2 distinct users; last-seat race stays within capacity")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
