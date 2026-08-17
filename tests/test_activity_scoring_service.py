"""Points/Ranks ToR phase 2: the verified-activity scoring engine and the
Event Scoring Profile built on top of it."""

from __future__ import annotations

import unittest
from datetime import date, time

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Event, EventRegistration, User
from app.services.activity_metrics_service import get_all_metrics, get_metric, increment_metric
from app.services.activity_scoring_service import (
    record_verified_activity,
    score_event_attendance,
    score_event_attendance_and_role,
    score_event_role_bonus,
)
from app.services.points_service import total_points
from app.utils.constants import EventParticipantRole, EventScoringPreset, PointCategory


class ActivityMetricsServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int = 1) -> User:
        user = User(telegram_id=telegram_id, first_name="Dev")
        session.add(user)
        await session.flush()
        return user

    async def test_increment_metric_creates_and_accumulates(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            await increment_metric(session, user_id=user.id, metric_key="events_attended", delta=1)
            await increment_metric(session, user_id=user.id, metric_key="events_attended", delta=1)
            self.assertEqual(
                await get_metric(session, user_id=user.id, metric_key="events_attended"), 2
            )

    async def test_get_metric_defaults_to_zero(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            self.assertEqual(
                await get_metric(session, user_id=user.id, metric_key="nonexistent"), 0
            )

    async def test_get_all_metrics(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            await increment_metric(session, user_id=user.id, metric_key="volunteer_hours", delta=4)
            await increment_metric(session, user_id=user.id, metric_key="events_attended", delta=1)
            self.assertEqual(
                await get_all_metrics(session, user_id=user.id),
                {"volunteer_hours": 4, "events_attended": 1},
            )


class RecordVerifiedActivityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int = 1) -> User:
        user = User(telegram_id=telegram_id, first_name="Dev")
        session.add(user)
        await session.flush()
        return user

    async def test_points_and_metrics_land_together(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            await record_verified_activity(
                session,
                user_id=user.id,
                points=50,
                reason="test",
                category=PointCategory.PROJECT,
                source_type="test_activity",
                source_id=1,
                idempotency_key="test:1",
                approved_by=user.id,
                metric_updates={"project_activities": 1, "events_attended": 0},
            )
            self.assertEqual(await total_points(session, user.id), 50)
            self.assertEqual(
                await get_metric(session, user_id=user.id, metric_key="project_activities"), 1
            )

    async def test_retry_does_not_double_pay_or_double_count(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            for _ in range(3):
                await record_verified_activity(
                    session,
                    user_id=user.id,
                    points=50,
                    reason="test",
                    category=PointCategory.PROJECT,
                    source_type="test_activity",
                    source_id=1,
                    idempotency_key="test:retry",
                    approved_by=user.id,
                    metric_updates={"project_activities": 1},
                )
            self.assertEqual(await total_points(session, user.id), 50)
            self.assertEqual(
                await get_metric(session, user_id=user.id, metric_key="project_activities"), 1
            )


class EventScoringProfileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int) -> User:
        user = User(telegram_id=telegram_id, first_name=f"P{telegram_id}")
        session.add(user)
        await session.flush()
        return user

    async def _make_event(self, session, *, created_by: int, points_for_visit: int = 100, preset: str = EventScoringPreset.STANDARD) -> Event:
        event = Event(
            title="Событие",
            description="d",
            event_date=date(2026, 1, 1),
            event_time=time(18, 0),
            location="Онлайн",
            format="online",
            points_for_visit=points_for_visit,
            created_by=created_by,
            scoring_preset=preset,
        )
        session.add(event)
        await session.flush()
        return event

    async def _make_registration(self, session, *, event_id: int, user_id: int, role: str = EventParticipantRole.PARTICIPANT, volunteer_hours: int | None = None) -> EventRegistration:
        registration = EventRegistration(
            event_id=event_id, user_id=user_id, role=role, volunteer_hours=volunteer_hours
        )
        session.add(registration)
        await session.flush()
        return registration

    async def test_plain_participant_gets_only_attendance_and_events_attended(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = await self._make_event(session, created_by=admin.id, preset=EventScoringPreset.VOLUNTEERING)
            registration = await self._make_registration(session, event_id=event.id, user_id=participant.id)

            awarded = await score_event_attendance_and_role(
                session, event, registration, participant, approved_by_id=admin.id
            )

            self.assertEqual(len(awarded), 1)
            self.assertEqual(await total_points(session, participant.id), 100)
            self.assertEqual(await get_metric(session, user_id=participant.id, metric_key="events_attended"), 1)
            # Plain attendance at a volunteering-preset event does not count
            # as a volunteer/social activity -- only real contributors do.
            self.assertEqual(await get_metric(session, user_id=participant.id, metric_key="volunteer_activities"), 0)

    async def test_volunteer_hours_capped_at_200(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            volunteer = await self._make_user(session, 2)
            event = await self._make_event(session, created_by=admin.id, preset=EventScoringPreset.VOLUNTEERING)
            registration = await self._make_registration(
                session, event_id=event.id, user_id=volunteer.id, role=EventParticipantRole.VOLUNTEER, volunteer_hours=10
            )

            await score_event_attendance_and_role(session, event, registration, volunteer, approved_by_id=admin.id)

            # attendance (100) + volunteer bonus capped at 200 (10h * 25 = 250 -> 200)
            self.assertEqual(await total_points(session, volunteer.id), 300)
            self.assertEqual(await get_metric(session, user_id=volunteer.id, metric_key="volunteer_hours"), 10)
            self.assertEqual(await get_metric(session, user_id=volunteer.id, metric_key="volunteer_activities"), 1)
            self.assertEqual(await get_metric(session, user_id=volunteer.id, metric_key="social_activities"), 1)

    async def test_organizer_gets_role_bonus_and_events_organized(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            organizer = await self._make_user(session, 2)
            event = await self._make_event(session, created_by=admin.id, preset=EventScoringPreset.VOLUNTEERING)
            registration = await self._make_registration(
                session, event_id=event.id, user_id=organizer.id, role=EventParticipantRole.ORGANIZER
            )

            await score_event_attendance_and_role(session, event, registration, organizer, approved_by_id=admin.id)

            self.assertEqual(await total_points(session, organizer.id), 100 + 250)
            self.assertEqual(await get_metric(session, user_id=organizer.id, metric_key="events_organized"), 1)
            self.assertEqual(await get_metric(session, user_id=organizer.id, metric_key="social_activities"), 1)

    async def test_speaker_role_bonus(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            speaker = await self._make_user(session, 2)
            event = await self._make_event(session, created_by=admin.id, preset=EventScoringPreset.LEADERSHIP)
            registration = await self._make_registration(
                session, event_id=event.id, user_id=speaker.id, role=EventParticipantRole.SPEAKER
            )

            await score_event_attendance_and_role(session, event, registration, speaker, approved_by_id=admin.id)

            self.assertEqual(await total_points(session, speaker.id), 100 + 150)
            # LEADERSHIP preset and the speaker role both map to
            # leadership_activities -- one real activity, not two.
            self.assertEqual(await get_metric(session, user_id=speaker.id, metric_key="leadership_activities"), 1)

    async def test_other_role_gets_no_automatic_bonus(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            person = await self._make_user(session, 2)
            event = await self._make_event(session, created_by=admin.id)
            registration = await self._make_registration(
                session, event_id=event.id, user_id=person.id, role=EventParticipantRole.OTHER
            )

            awarded = await score_event_attendance_and_role(session, event, registration, person, approved_by_id=admin.id)

            self.assertEqual(len(awarded), 1)
            self.assertEqual(await total_points(session, person.id), 100)

    async def test_score_event_role_bonus_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            organizer = await self._make_user(session, 2)
            event = await self._make_event(session, created_by=admin.id)
            registration = await self._make_registration(
                session, event_id=event.id, user_id=organizer.id, role=EventParticipantRole.ORGANIZER
            )

            await score_event_role_bonus(session, event, registration, organizer, approved_by_id=admin.id)
            await score_event_role_bonus(session, event, registration, organizer, approved_by_id=admin.id)

            self.assertEqual(await total_points(session, organizer.id), 250)
            self.assertEqual(await get_metric(session, user_id=organizer.id, metric_key="events_organized"), 1)

    async def test_score_event_attendance_reuses_existing_idempotency_key(self) -> None:
        """Same idempotency key format as every other attendance-award call
        site (event_attendance:{event}:{user}) -- calling this after one of
        the legacy paths already paid must not double-pay."""
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = await self._make_event(session, created_by=admin.id)
            registration = await self._make_registration(session, event_id=event.id, user_id=participant.id)

            from app.services.points_service import add_points

            await add_points(
                session,
                user_id=participant.id,
                points=event.points_for_visit,
                reason="legacy award",
                approved_by=admin.id,
                related_event_id=event.id,
                source_type="event_attendance",
                source_id=registration.id,
                idempotency_key=f"event_attendance:{event.id}:{participant.id}",
            )

            await score_event_attendance(session, event, registration, participant, approved_by_id=admin.id)

            self.assertEqual(await total_points(session, participant.id), 100)


if __name__ == "__main__":
    unittest.main()
