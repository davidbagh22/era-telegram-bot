from __future__ import annotations

import unittest
from datetime import date, time

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Event, EventActivity, EventActivitySubmission, User
from app.services.activity_metrics_service import get_metric
from app.services.event_activity_scoring_service import score_event_activity_completion
from app.services.points_service import total_points


class EventActivityScoringTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_verified_activity_updates_points_metrics_and_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            admin = User(telegram_id=100, first_name="Admin", role="admin")
            participant = User(telegram_id=101, first_name="Participant")
            session.add_all([admin, participant])
            await session.flush()
            event = Event(
                title="ERA Event",
                description="d",
                event_date=date.today(),
                event_time=time(18, 0),
                location="Yerevan",
                format="offline",
                created_by=admin.id,
            )
            session.add(event)
            await session.flush()
            activity = EventActivity(
                event_id=event.id,
                title="Verified follow-up",
                description="Result",
                submission_type="text",
                points=80,
                requires_review=True,
                is_active=True,
            )
            session.add(activity)
            await session.flush()
            submission = EventActivitySubmission(
                activity_id=activity.id,
                user_id=participant.id,
                text="done",
                status="pending",
            )
            session.add(submission)
            await session.flush()

            first = await score_event_activity_completion(
                session,
                activity=activity,
                submission=submission,
                participant=participant,
                approved_by_id=admin.id,
            )
            second = await score_event_activity_completion(
                session,
                activity=activity,
                submission=submission,
                participant=participant,
                approved_by_id=admin.id,
            )

            self.assertEqual(first.id, second.id)
            self.assertEqual(await total_points(session, participant.id), 80)
            self.assertEqual(
                await get_metric(session, user_id=participant.id, metric_key="event_activities"),
                1,
            )
            self.assertEqual(first.source_type, "event_activity")
            self.assertEqual(first.related_event_id, event.id)


if __name__ == "__main__":
    unittest.main()
