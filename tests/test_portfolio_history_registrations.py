"""Profile history keeps only attended events; registrations stay separate."""

from __future__ import annotations

import unittest
from datetime import date, time, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Event, EventRegistration, User
from app.services.portfolio_service import build_portfolio_data
from app.utils.constants import EventStatus, RegistrationStatus


class PortfolioHistoryRegistrationsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_attended_events_in_history_registrations_separate(self) -> None:
        async with self.session_factory() as session:
            user = User(
                telegram_id=901,
                first_name="Anna",
                phone="+10000000001",
                city="Yerevan",
                education_work="Study",
                occupation="Student",
                motivation="Grow",
                available_time="Evenings",
                desired_path="participant",
                personal_data_consent=True,
                is_channel_subscribed=True,
                role="participant",
            )
            session.add(user)
            await session.flush()

            attended = Event(
                title="Attended meetup",
                description="ok",
                event_date=date.today() - timedelta(days=3),
                event_time=time(18, 0),
                location="Hall",
                format="offline",
                created_by=user.id,
                status=EventStatus.COMPLETED,
            )
            registered = Event(
                title="Only registered",
                description="soon",
                event_date=date.today() + timedelta(days=5),
                event_time=time(19, 0),
                location="Hall",
                format="offline",
                created_by=user.id,
                status=EventStatus.REGISTRATION_OPEN,
            )
            session.add_all([attended, registered])
            await session.flush()
            session.add_all(
                [
                    EventRegistration(
                        event_id=attended.id,
                        user_id=user.id,
                        status=RegistrationStatus.ATTENDED,
                    ),
                    EventRegistration(
                        event_id=registered.id,
                        user_id=user.id,
                        status=RegistrationStatus.REGISTERED,
                    ),
                ]
            )
            await session.flush()

            data = await build_portfolio_data(session, user)
            self.assertEqual([item.title for item in data.events], ["Attended meetup"])
            self.assertEqual([item.title for item in data.registrations], ["Only registered"])
            self.assertEqual(data.events[0].status, "Посетил")
            self.assertEqual(data.registrations[0].status, "Зарегистрирован")
