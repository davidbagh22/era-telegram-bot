"""Malformed notice isolation and worker locking on disposable PostgreSQL only."""
import asyncio
import json
import os
import uuid
from datetime import date, time
from unittest.mock import AsyncMock, patch

from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import AppSetting, Event, User
from app.services.event_attendance_service import deliver_attendance_notifications
from app.utils.constants import ApplicationStatus, EventStatus


async def main():
    url = make_url(os.environ["DATABASE_URL"])
    if (url.get_backend_name() != "postgresql" or url.database != "era_test"
            or url.host not in {"127.0.0.1", "localhost"}):
        raise RuntimeError("Only disposable local PostgreSQL era_test is allowed")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    token = uuid.uuid4().hex
    prefix = f"event-lifecycle:pending:ci-{token}-"
    owner_id = event_id = None
    try:
        async with sessions() as session:
            # The worker scans all pending rows: refuse any pre-existing workload.
            assert await session.scalar(select(AppSetting.key).where(
                AppSetting.key.like("event-lifecycle:pending:%")).limit(1)) is None
            owner = User(telegram_id=90_000_000_000 + int(token[:7], 16),
                         first_name="CI notices", application_status=ApplicationStatus.APPROVED)
            session.add(owner)
            await session.flush()
            owner_id = owner.id
            event = Event(title="CI notice", description="Disposable fixture",
                          event_date=date.today(), event_time=time(12), location="Online",
                          format="online", created_by=owner.id, status=EventStatus.ACTIVE)
            session.add(event)
            await session.flush()
            event_id = event.id
            good = dict(status="pending", event_id=event.id, phase="start",
                        title=event.title, location=event.location, recipients=[])
            healthy_key = f"event-lifecycle:pending:{event.id}:start"
            malformed = {
                "wrong-identity": good,
                "json": "{broken", "array": [], "null": None,
                "recipients": {**good, "recipients": [True]},
                "attempts": {**good, "attempts": "0"},
            }
            session.add_all([AppSetting(key=prefix + name, value=value)
                             for name, value in malformed.items()])
            session.add(AppSetting(key=healthy_key, value=json.dumps(good)))
            await session.commit()

        sender = AsyncMock(side_effect=AssertionError("Probe must never send Telegram messages"))
        with patch("app.services.event_attendance_service.safe_send_once", sender):
            results = await asyncio.wait_for(asyncio.gather(*(
                deliver_attendance_notifications(None, None, sessions) for _ in range(8))), 45)
        assert results == [0] * 8, results
        sender.assert_not_awaited()
        async with sessions() as session:
            for name, value in malformed.items():
                row = await session.scalar(select(AppSetting).where(AppSetting.key == prefix + name))
                assert row is not None and row.value == value, name
            assert await session.scalar(select(AppSetting).where(
                AppSetting.key == healthy_key)) is None
            sent = await session.scalar(select(AppSetting).where(
                AppSetting.key == (healthy_key).replace(":pending:", ":sent:", 1)))
            assert sent is not None
            payload = json.loads(sent.value)
            assert payload["status"] == "sent" and payload["attempts"] == 1, payload
        print("Lifecycle PostgreSQL: corrupt rows unchanged, 8 workers -> 1 transition, no sends")
    finally:
        async with sessions() as session:
            await session.execute(delete(AppSetting).where(AppSetting.key.like(f"event-lifecycle:%:ci-{token}-%")))
            if event_id is not None:
                await session.execute(delete(AppSetting).where(AppSetting.key.in_([
                    f"event-lifecycle:pending:{event_id}:start",
                    f"event-lifecycle:sent:{event_id}:start"])))
                await session.execute(delete(Event).where(Event.id == event_id))
            if owner_id is not None:
                await session.execute(delete(User).where(User.id == owner_id))
            await session.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
