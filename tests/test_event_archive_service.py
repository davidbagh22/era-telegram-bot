"""Auto-archive uses COMPLETED; never deletes registrations or points."""

from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.event_attendance import EventAttendanceSession
from app.database.models import Event, EventRegistration, User
from app.services.event_archive_service import (
    archive_elapsed_events,
    close_elapsed_attendance_windows,
)
from app.utils.constants import EventStatus, RegistrationStatus

TZ = "Asia/Yerevan"


class EventArchiveServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _user(self, session) -> User:
        user = User(
            telegram_id=501,
            first_name="Archive",
            phone="+10000000501",
            city="Yerevan",
            education_work="Work",
            occupation="Occ",
            motivation="M",
            available_time="Evenings",
            desired_path="participant",
            personal_data_consent=True,
            is_channel_subscribed=True,
            role="admin",
        )
        session.add(user)
        await session.flush()
        return user

    async def test_archives_elapsed_public_event_after_24h_keeps_registration(self) -> None:
        zone = ZoneInfo(TZ)
        now = datetime(2026, 11, 17, 12, 0, tzinfo=zone)
        async with self.session_factory() as session:
            user = await self._user(session)
            event = Event(
                title="Past meetup",
                description="d",
                event_date=(now - timedelta(days=2)).date(),
                event_time=time(10, 0),
                location="Hall",
                format="offline",
                created_by=user.id,
                status=EventStatus.REGISTRATION_OPEN,
            )
            session.add(event)
            await session.flush()
            session.add(
                EventRegistration(
                    event_id=event.id,
                    user_id=user.id,
                    status=RegistrationStatus.REGISTERED,
                )
            )
            await session.flush()

            archived = await archive_elapsed_events(session, timezone=TZ, now=now)
            self.assertEqual(archived, [event.id])
            self.assertEqual(event.status, EventStatus.COMPLETED)
            registration = await session.scalar(
                select(EventRegistration).where(EventRegistration.event_id == event.id)
            )
            self.assertEqual(registration.status, RegistrationStatus.REGISTERED)

    async def test_keeps_upcoming_events_on_board(self) -> None:
        zone = ZoneInfo(TZ)
        now = datetime(2026, 11, 17, 12, 0, tzinfo=zone)
        async with self.session_factory() as session:
            user = await self._user(session)
            event = Event(
                title="Future meetup",
                description="d",
                event_date=(now + timedelta(days=3)).date(),
                event_time=time(18, 0),
                location="Hall",
                format="offline",
                created_by=user.id,
                status=EventStatus.PUBLISHED,
            )
            session.add(event)
            await session.flush()
            archived = await archive_elapsed_events(session, timezone=TZ, now=now)
            self.assertEqual(archived, [])
            self.assertEqual(event.status, EventStatus.PUBLISHED)

    async def test_force_archives_project_accelerator(self) -> None:
        zone = ZoneInfo(TZ)
        now = datetime(2026, 11, 17, 12, 0, tzinfo=zone)
        async with self.session_factory() as session:
            user = await self._user(session)
            # Still on the board somehow despite old date.
            event = Event(
                title="Проектный акселератор",
                description="d",
                event_date=date(2026, 8, 29),
                event_time=time(10, 0),
                location="Дом Москвы",
                format="offline",
                created_by=user.id,
                status=EventStatus.REGISTRATION_OPEN,
            )
            session.add(event)
            await session.flush()
            archived = await archive_elapsed_events(session, timezone=TZ, now=now)
            self.assertEqual(archived, [event.id])
            self.assertEqual(event.status, EventStatus.COMPLETED)

    async def test_active_archive_opens_attendance_confirmation(self) -> None:
        zone = ZoneInfo(TZ)
        now = datetime(2026, 11, 17, 12, 0, tzinfo=zone)
        async with self.session_factory() as session:
            user = await self._user(session)
            event = Event(
                title="Started meetup",
                description="d",
                event_date=(now - timedelta(days=2)).date(),
                event_time=time(10, 0),
                location="Hall",
                format="offline",
                created_by=user.id,
                status=EventStatus.ACTIVE,
            )
            session.add(event)
            await session.flush()
            session.add(
                EventAttendanceSession(
                    event_id=event.id,
                    attendance_code=None,
                    started_at=now - timedelta(days=2),
                    started_by=user.id,
                )
            )
            await session.flush()

            archived = await archive_elapsed_events(session, timezone=TZ, now=now)
            self.assertEqual(archived, [event.id])
            self.assertEqual(event.status, EventStatus.COMPLETED)
            runtime = await session.get(EventAttendanceSession, event.id)
            self.assertIsNotNone(runtime.attendance_code)
            self.assertIsNotNone(runtime.completed_at)
            self.assertIsNone(runtime.confirmation_closed_at)

    async def test_closes_attendance_window_after_7_days(self) -> None:
        zone = ZoneInfo(TZ)
        now = datetime(2026, 11, 17, 12, 0, tzinfo=zone)
        async with self.session_factory() as session:
            user = await self._user(session)
            event = Event(
                title="Ended",
                description="d",
                event_date=(now - timedelta(days=10)).date(),
                event_time=time(10, 0),
                location="Hall",
                format="offline",
                created_by=user.id,
                status=EventStatus.COMPLETED,
            )
            session.add(event)
            await session.flush()
            session.add(
                EventAttendanceSession(
                    event_id=event.id,
                    attendance_code="AB12CD",
                    completed_at=now - timedelta(days=10),
                )
            )
            await session.flush()
            closed = await close_elapsed_attendance_windows(session, timezone=TZ, now=now)
            self.assertEqual(closed, [event.id])
            runtime = await session.get(EventAttendanceSession, event.id)
            self.assertIsNotNone(runtime.confirmation_closed_at)
