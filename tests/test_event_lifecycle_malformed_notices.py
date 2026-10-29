"""Malformed lifecycle notices must not block healthy pending events.

Uses an isolated SQLite database and zero recipients: no Telegram API calls,
real attendance, points or production state are touched.
"""
import json
import unittest
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting, Event, User
from app.services.event_attendance_service import (
    _validated_pending_lifecycle_notice,
    deliver_attendance_notifications,
)
from app.utils.constants import ApplicationStatus, EventStatus


class PendingLifecycleNoticeValidationTests(unittest.IsolatedAsyncioTestCase):
    def test_preflight_rejects_bad_json_and_unsafe_recipient_shapes(self):
        valid = {
            "status": "pending", "event_id": 42, "phase": "start",
            "title": "Fixture", "location": "Online", "recipients": [],
        }
        self.assertEqual(_validated_pending_lifecycle_notice(valid), valid)
        for invalid in (
            "{bad json", [], None, 42, {"status": "pending"},
            {**valid, "event_id": True}, {**valid, "event_id": 2_147_483_648},
            {**valid, "phase": "unknown"}, {**valid, "title": None},
            {**valid, "recipients": "123"}, {**valid, "recipients": [True]},
            {**valid, "recipients": ["123"]}, {**valid, "attempts": -1},
            {**valid, "attempts": "0"},
        ):
            with self.subTest(value=str(invalid)[:60]):
                self.assertIsNone(_validated_pending_lifecycle_notice(invalid))

    async def test_corrupt_notice_is_unchanged_and_healthy_event_is_processed(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                owner = User(
                    telegram_id=99123456, first_name="Fixture",
                    application_status=ApplicationStatus.APPROVED,
                )
                session.add(owner)
                await session.flush()
                event = Event(
                    title="Fixture", description="Isolated test",
                    event_date=date.today(), event_time=time(12),
                    location="Online", format="online",
                    created_by=owner.id, status=EventStatus.ACTIVE,
                )
                session.add(event)
                await session.flush()
                good = {
                    "status": "pending", "event_id": event.id,
                    "phase": "start", "title": event.title,
                    "location": event.location, "recipients": [],
                }
                session.add_all([
                    AppSetting(key="event-lifecycle:pending:bad-json", value="{not-json"),
                    AppSetting(
                        key="event-lifecycle:pending:bad-recipients",
                        value={**good, "recipients": "wrong-type"},
                    ),
                    AppSetting(key="event-lifecycle:pending:healthy", value=json.dumps(good)),
                ])
                await session.commit()

            with self.assertLogs("app.services.event_attendance_service", level="WARNING") as logs:
                delivered = await deliver_attendance_notifications(None, None, factory)
            self.assertEqual(delivered, 0)
            self.assertEqual(len(logs.output), 2)
            async with factory() as session:
                keys = set((await session.scalars(select(AppSetting.key))).all())
                self.assertIn("event-lifecycle:pending:bad-json", keys)
                self.assertIn("event-lifecycle:pending:bad-recipients", keys)
                self.assertIn("event-lifecycle:sent:healthy", keys)
                self.assertNotIn("event-lifecycle:pending:healthy", keys)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
