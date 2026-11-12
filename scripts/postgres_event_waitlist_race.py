#!/usr/bin/env python3
"""Prove event capacity and waitlist promotions under PostgreSQL concurrency."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.admin_event_create import EventDraftPatch, save_event_draft_step
from app.api.v1.events import register_event
from app.config import Settings
from app.database.event_experience import EventExperience
from app.database.models import Event, EventRegistration, User
from app.database.system_models import NotificationDelivery
from app.services.event_registration_notice_service import (
    RegistrationNoticeKind,
    deliver_registration_notice,
    enqueue_registration_notice,
)
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
    settings = Settings(bot_token="0000000000:POSTGRESMIGRATIONSMOKE")
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
            event_fields = dict(
                description="Disposable PostgreSQL concurrency fixture",
                event_date=date.today() + timedelta(days=3),
                event_time=time(18),
                location="CI only",
                format="Offline",
                participant_limit=1,
                created_by=creator.id,
                status=EventStatus.REGISTRATION_OPEN,
            )
            event = Event(title=f"CI capacity {nonce}", **event_fields)
            legacy = Event(title=f"CI legacy {nonce}", **event_fields)
            session.add_all([event, legacy])
            await session.flush()
            session.add(EventExperience(event_id=event.id, waitlist_enabled=True))
            await session.commit()
            event_id, legacy_id = event.id, legacy.id
            participant_ids = [participant.id for participant in participants]

        async def register(user_id: int) -> str:
            async with sessions() as session:
                current_event = await session.get(Event, event_id)
                registration, error = await register_for_event(session, current_event, user_id)
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
                registration, error = await register_for_event(session, current_event, user_id)
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
            cancelled_user_id = registered.user_id
            registered.status = RegistrationStatus.CANCELLED
            await session.commit()

        barrier = asyncio.Barrier(len(participant_ids))

        async def promote() -> int | None:
            await barrier.wait()
            async with sessions() as session:
                current_event = await session.get(Event, event_id)
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

        async def race_admin_policy(
            target_id: int, patch: EventDraftPatch, expected_error: str | None, *, rollback_edit: bool = False
        ) -> None:
            async with sessions() as applicant, sessions() as editor:
                stale_event = await applicant.get(Event, target_id)
                stale_policy = await applicant.get(EventExperience, target_id)
                assert (stale_policy is None) == (target_id == legacy_id)
                await save_event_draft_step(target_id, patch, creator, editor, settings, None)

                task = asyncio.create_task(register_for_event(applicant, stale_event, creator.id))
                try:
                    done, _ = await asyncio.wait({task}, timeout=0.15)
                    assert not done, "Registration bypassed the admin's Event lock"
                    if rollback_edit:
                        await editor.rollback()
                    else:
                        await editor.commit()
                    registration, error = await asyncio.wait_for(task, timeout=10)
                    assert error == expected_error, (registration, error)
                    if expected_error is None:
                        assert registration is not None and registration.status == RegistrationStatus.REGISTERED
                    else:
                        assert registration is None
                    if expected_error == "full":
                        assert not stale_policy.waitlist_enabled
                finally:
                    if not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)

        await race_admin_policy(event_id, EventDraftPatch(waitlist_enabled=False), "full")
        await race_admin_policy(
            event_id, EventDraftPatch(registration_close_at=datetime.now(timezone.utc) - timedelta(minutes=1)), "closed"
        )
        await race_admin_policy(
            legacy_id, EventDraftPatch(registration_required=False), None, rollback_edit=True
        )
        await race_admin_policy(legacy_id, EventDraftPatch(registration_required=False), "registration_not_required")

        async with sessions() as editor:
            edited_event = await editor.get(Event, event_id)
            experience = await editor.get(EventExperience, event_id)
            experience.registration_close_at = None
            edited_event.participant_limit = 2
            await editor.commit()

        async with sessions() as joiner, sessions() as promoter:
            join_event = await joiner.get(Event, event_id)
            promote_event = await promoter.get(Event, event_id)
            assert join_event.participant_limit == promote_event.participant_limit == 2

            async with sessions() as editor:
                edited_event = await editor.get(Event, event_id)
                edited_event.participant_limit = 1
                await editor.commit()

            registration, error = await register_for_event(joiner, join_event, cancelled_user_id)
            assert registration is None and error == "full", (registration, error)
            await joiner.rollback()
            assert await promote_waitlist(promoter, promote_event) is None
            await promoter.rollback()

        async with sessions() as editor:
            edited_event = await editor.get(Event, event_id)
            edited_event.participant_limit = 2
            await editor.commit()

        send_started = asyncio.Event()
        finish_send = asyncio.Event()
        send_transactions = []

        async def register_with_delayed_notice() -> str:
            async with sessions() as session:
                async def send_message(*args, **kwargs):
                    send_transactions.append(session.in_transaction())
                    send_started.set()
                    await finish_send.wait()

                user = await session.get(User, cancelled_user_id)
                bot = SimpleNamespace(send_message=send_message)
                result = await register_event(event_id, user, session, bot, settings)
                return result.registration_status

        pending_notice = asyncio.create_task(register_with_delayed_notice())
        try:
            await asyncio.wait_for(send_started.wait(), timeout=10)
            async with sessions() as competitor:
                other_user = await competitor.get(User, creator.id)
                try:
                    await asyncio.wait_for(
                        register_event(event_id, other_user, competitor, None, settings), timeout=10
                    )
                except HTTPException as exc:
                    assert (exc.status_code, exc.detail) == (409, "full"), exc
                else:
                    raise AssertionError("A competing request overbooked the committed last seat")
            assert not pending_notice.done()
        finally:
            finish_send.set()
            confirmed_status = await asyncio.wait_for(pending_notice, timeout=10)
        assert confirmed_status == RegistrationStatus.REGISTERED, confirmed_status
        assert send_transactions == [False], send_transactions

        async with sessions() as session, session.begin():
            registration = await session.scalar(select(EventRegistration).where(
                EventRegistration.event_id == event_id, EventRegistration.user_id == cancelled_user_id,
            ))
            user = await session.get(User, cancelled_user_id)
            assert registration is not None and user is not None
            recipient = user.telegram_id
            key = await enqueue_registration_notice(session, registration, recipient, RegistrationNoticeKind.TELEGRAM)

        sent_to = []

        async def recover_notice() -> None:
            async with sessions() as session:
                async def send(chat_id, _text, **kwargs):
                    sent_to.append((chat_id, session.in_transaction()))
                    return SimpleNamespace(message_id=712)

                await deliver_registration_notice(session, key, send, settings)

        await asyncio.wait_for(asyncio.gather(recover_notice(), recover_notice()), timeout=10)
        assert sent_to == [(recipient, False)], sent_to
        async with sessions() as session:
            receipt = await session.scalar(select(NotificationDelivery).where(NotificationDelivery.delivery_key == key))
            assert (receipt.status, receipt.attempt_count, receipt.message_id) == ("sent", 1, 712)

        print("PostgreSQL event capacity/waitlist concurrency verification passed")
        print("registrations=8 capacity=1 registered=1 waitlist=7 duplicate_replays=8 promotions=1")
        print("after_release registered=1 waitlist=6 total_rows=8; stale capacity rejected")
        print("Registration honored the admin edit, deadline, waitlist, and legacy policy commit or rollback")
        print("A concurrent request saw the committed last seat while Telegram delivery was paused")
        print("Two workers competing for one queued notice attempted delivery once")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
