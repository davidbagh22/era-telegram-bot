from __future__ import annotations

import unittest
from datetime import date, time

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Event, EventRegistration, User
from app.services import event_registration_service as svc
from app.utils.constants import EventStatus, RegistrationStatus


class EventRegistrationServiceOperationsTests(unittest.IsolatedAsyncioTestCase):
    """Post-moderation event operations — participants, attendance, points —
    mirrors app/handlers/admin/event_registration_block14.py exactly,
    including its idempotency key, so re-awarding never double-pays."""

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

    def _event(self, *, created_by: int, status: str = EventStatus.REGISTRATION_OPEN, points: int = 5) -> Event:
        return Event(
            title="Событие",
            description="d",
            event_date=date(2026, 1, 1),
            event_time=time(18, 0),
            location="Онлайн",
            format="online",
            status=status,
            points_for_visit=points,
            created_by=created_by,
        )

    async def test_list_operational_excludes_draft_pending_cancelled(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            draft = self._event(created_by=admin.id, status=EventStatus.DRAFT)
            pending = self._event(created_by=admin.id, status=EventStatus.PENDING_APPROVAL)
            cancelled = self._event(created_by=admin.id, status=EventStatus.CANCELLED)
            live = self._event(created_by=admin.id, status=EventStatus.REGISTRATION_OPEN)
            session.add_all([draft, pending, cancelled, live])
            await session.flush()

            rows = await svc.list_operational_events(session)
            self.assertEqual({e.id for e in rows}, {live.id})

    async def test_list_participants_and_set_attendance(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            participant = await self._make_user(session, 2)
            event = self._event(created_by=admin.id)
            session.add(event)
            await session.flush()
            registration = EventRegistration(event_id=event.id, user_id=participant.id)
            session.add(registration)
            await session.flush()

            rows = await svc.list_participants(session, event.id)
            self.assertEqual(len(rows), 1)
            reg, user = rows[0]
            self.assertEqual(user.id, participant.id)

            svc.set_attendance(reg, True)
            self.assertEqual(reg.status, RegistrationStatus.ATTENDED)
            svc.set_attendance(reg, False)
            self.assertEqual(reg.status, RegistrationStatus.NO_SHOW)

    async def test_award_attendance_points_only_pays_attended_once(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            attended = await self._make_user(session, 2)
            no_show = await self._make_user(session, 3)
            event = self._event(created_by=admin.id, points=7)
            session.add(event)
            await session.flush()
            reg_attended = EventRegistration(
                event_id=event.id, user_id=attended.id, status=RegistrationStatus.ATTENDED
            )
            reg_no_show = EventRegistration(
                event_id=event.id, user_id=no_show.id, status=RegistrationStatus.NO_SHOW
            )
            session.add_all([reg_attended, reg_no_show])
            await session.flush()

            newly_awarded = await svc.award_attendance_points(session, event, approved_by_id=admin.id)
            self.assertEqual([u.id for u in newly_awarded], [attended.id])

            # Re-running (e.g. after marking one more person attended) must
            # not pay the same person twice.
            again = await svc.award_attendance_points(session, event, approved_by_id=admin.id)
            self.assertEqual(again, [])

    async def test_award_attendance_points_applies_event_scoring_role_bonus(self) -> None:
        """award_attendance_points (the Mini App admin bulk-award path) now
        routes through activity_scoring_service, so a registration's role
        picks up its bonus automatically alongside the base attendance
        points -- Points/Ranks ToR phase 2."""
        from app.services.activity_metrics_service import get_metric
        from app.services.points_service import total_points
        from app.utils.constants import EventParticipantRole

        async with self.session_factory() as session:
            admin = await self._make_user(session, 1)
            organizer = await self._make_user(session, 2)
            event = self._event(created_by=admin.id, points=100)
            session.add(event)
            await session.flush()
            registration = EventRegistration(
                event_id=event.id,
                user_id=organizer.id,
                status=RegistrationStatus.ATTENDED,
                role=EventParticipantRole.ORGANIZER,
            )
            session.add(registration)
            await session.flush()

            await svc.award_attendance_points(session, event, approved_by_id=admin.id)

            self.assertEqual(await total_points(session, organizer.id), 100 + 250)
            self.assertEqual(
                await get_metric(session, user_id=organizer.id, metric_key="events_attended"), 1
            )
            self.assertEqual(
                await get_metric(session, user_id=organizer.id, metric_key="events_organized"), 1
            )


if __name__ == "__main__":
    unittest.main()
