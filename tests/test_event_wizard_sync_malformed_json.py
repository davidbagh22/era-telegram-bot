from __future__ import annotations

import unittest
from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import Event, EventActivity, User
from app.services.event_wizard_sync_service import sync_event_wizard_tasks
from app.utils.constants import EventStatus


class EventWizardMalformedJsonRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _event(self, session, created_by, *, tasks, activity_ids=None):
        event = Event(
            title="Wizard recovery test",
            description="No Telegram delivery",
            event_date=date.today() + timedelta(days=3),
            event_time=time(18),
            location="Test",
            format="Офлайн",
            participant_limit=20,
            created_by=created_by,
            status=EventStatus.PUBLISHED,
        )
        session.add(event)
        await session.flush()
        session.add(EventExperience(
            event_id=event.id,
            is_complete=True,
            participant_tasks=tasks,
            participant_task_activity_ids=activity_ids if activity_ids is not None else [],
        ))
        return event.id

    async def test_bad_json_is_skipped_without_stopping_healthy_events(self):
        async with self.sessions() as session:
            admin = User(
                telegram_id=8877001,
                first_name="Admin",
                phone="+10000008877001",
                personal_data_consent=True,
                is_channel_subscribed=True,
                role="admin",
            )
            session.add(admin)
            await session.flush()
            bad_ids = [
                await self._event(session, admin.id, tasks=["not an object"]),
                await self._event(session, admin.id, tasks=[{"title": "Broken", "points": "invalid"}]),
                await self._event(session, admin.id, tasks={"title": "not a list"}),
                await self._event(session, admin.id, tasks=[{"title": "Task", "points": 3}], activity_ids=["invalid"]),
            ]
            good_id = await self._event(session, admin.id, tasks=[{"title": "Good", "points": 7}])
            await session.commit()

        async with self.sessions() as session:
            with self.assertLogs("app.services.event_wizard_sync_service", level="WARNING") as captured:
                changed = await sync_event_wizard_tasks(session)
            self.assertEqual(changed, 2)
            self.assertEqual(len(captured.output), len(bad_ids))
            rows = list((await session.scalars(select(EventActivity))).all())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].event_id, good_id)
            self.assertEqual(rows[0].title, "Good")
            self.assertEqual(rows[0].points, 7)
            for event_id in bad_ids:
                experience = await session.get(EventExperience, event_id)
                self.assertEqual(experience.participant_task_activity_ids, ["invalid"] if event_id == bad_ids[-1] else [])

        async with self.sessions() as session:
            with self.assertLogs("app.services.event_wizard_sync_service", level="WARNING"):
                self.assertEqual(await sync_event_wizard_tasks(session), 0)
            self.assertEqual(len(list((await session.scalars(select(EventActivity))).all())), 1)


if __name__ == "__main__":
    unittest.main()
