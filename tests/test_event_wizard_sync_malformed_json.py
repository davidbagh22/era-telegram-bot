from __future__ import annotations

import unittest
from datetime import date, time, timedelta
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.event_experience import EventExperience
from app.database.models import Event, EventActivity, User
from app.services.event_wizard_sync_service import (
    _validated_task_configuration, sync_event_wizard_tasks,
)
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
                await self._event(session, admin.id, tasks=[{"title": "x" * 256, "points": 3}]),
                await self._event(session, admin.id, tasks=[{"title": "Overflow", "points": 2_147_483_648}]),
                await self._event(session, admin.id, tasks=[{"title": "Task", "points": 3}], activity_ids=[2_147_483_648]),
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
                self.assertEqual(experience.participant_task_activity_ids, ["invalid"] if event_id == bad_ids[3] else ([2_147_483_648] if event_id == bad_ids[-1] else []))

        async with self.sessions() as session:
            with self.assertLogs("app.services.event_wizard_sync_service", level="WARNING"):
                self.assertEqual(await sync_event_wizard_tasks(session), 0)
            self.assertEqual(len(list((await session.scalars(select(EventActivity))).all())), 1)


    def test_falsey_malformed_containers_are_not_silently_treated_as_empty(self):
        for bad in ({}, "", 0, False):
            with self.subTest(field="tasks", bad=bad):
                self.assertIsNone(_validated_task_configuration(SimpleNamespace(
                    participant_tasks=bad, participant_task_activity_ids=[],
                )))
            with self.subTest(field="activity_ids", bad=bad):
                self.assertIsNone(_validated_task_configuration(SimpleNamespace(
                    participant_tasks=[{"title": "Keep", "points": 7}],
                    participant_task_activity_ids=bad,
                )))
        self.assertEqual(_validated_task_configuration(SimpleNamespace(
            participant_tasks=None, participant_task_activity_ids=None,
        )), ([], []))

    async def test_falsey_corruption_preserves_existing_activity_and_ids(self):
        async with self.sessions() as session:
            admin = User(telegram_id=8877002, first_name="Admin")
            session.add(admin)
            await session.flush()
            corrupt_tasks_id = await self._event(
                session, admin.id, tasks={}, activity_ids=[],
            )
            corrupt_ids_id = await self._event(
                session, admin.id,
                tasks=[{"title": "Would duplicate", "points": 7}],
                activity_ids={},
            )
            activity = EventActivity(
                event_id=corrupt_tasks_id, title="Existing",
                description="Must stay active", points=7, is_active=True,
            )
            session.add(activity)
            await session.flush()
            experience = await session.get(EventExperience, corrupt_tasks_id)
            experience.participant_task_activity_ids = [activity.id]
            existing_id = activity.id
            await session.commit()

        async with self.sessions() as session:
            with self.assertLogs(
                "app.services.event_wizard_sync_service", level="WARNING",
            ) as warnings:
                self.assertEqual(await sync_event_wizard_tasks(session), 0)
            self.assertEqual(len(warnings.output), 2)
            existing = await session.get(EventActivity, existing_id)
            self.assertTrue(existing.is_active)
            self.assertEqual(existing.points, 7)
            experience = await session.get(EventExperience, corrupt_tasks_id)
            self.assertEqual(experience.participant_task_activity_ids, [existing_id])
            other = await session.get(EventExperience, corrupt_ids_id)
            self.assertEqual(other.participant_task_activity_ids, {})
            self.assertEqual(
                len(list((await session.scalars(select(EventActivity))).all())), 1,
            )


if __name__ == "__main__":
    unittest.main()
