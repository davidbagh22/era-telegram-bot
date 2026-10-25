from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.database.models import User
from app.database.participation_models import ParticipationLifecycle
from app.database.participation_notification_models import ParticipationModeDelivery
from app.services.participation_mode_notification_service import (
    _process_observer_checkins,
    _process_pause_reminders,
)
from app.utils.constants import ApplicationStatus


class ParticipationModeNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.bot = SimpleNamespace(send_message=AsyncMock(return_value=True))
        self.now = datetime(2026, 8, 19, 10, tzinfo=timezone.utc)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _user(self, session, telegram_id: int) -> User:
        user = User(
            telegram_id=telegram_id,
            first_name="Test",
            application_status=ApplicationStatus.APPROVED,
        )
        session.add(user)
        await session.flush()
        return user

    async def test_pause_end_reminder_is_sent_once_for_same_pause(self) -> None:
        async with self.sessions() as session:
            user = await self._user(session, 7001)
            lifecycle = ParticipationLifecycle(
                user_id=user.id,
                participation_mode="PAUSED",
                activity_state="INACTIVE",
                state_since=self.now - timedelta(days=40),
                mode_changed_at=self.now - timedelta(days=20),
                pause_until=(self.now + timedelta(days=2)).date(),
                onboarding_version=1,
            )
            session.add(lifecycle)
            await session.flush()

            await _process_pause_reminders(self.bot, session, self.now)
            await _process_pause_reminders(self.bot, session, self.now)

            self.assertEqual(self.bot.send_message.await_count, 1)
            deliveries = int(
                await session.scalar(
                    select(func.count()).select_from(ParticipationModeDelivery).where(
                        ParticipationModeDelivery.user_id == user.id,
                        ParticipationModeDelivery.kind == "pause_end",
                    )
                )
                or 0
            )
            self.assertEqual(deliveries, 1)

    async def test_pause_outside_three_day_window_does_not_notify(self) -> None:
        async with self.sessions() as session:
            user = await self._user(session, 7002)
            session.add(
                ParticipationLifecycle(
                    user_id=user.id,
                    participation_mode="PAUSED",
                    activity_state="INACTIVE",
                    state_since=self.now - timedelta(days=40),
                    mode_changed_at=self.now - timedelta(days=5),
                    pause_until=(self.now + timedelta(days=10)).date(),
                    onboarding_version=1,
                )
            )
            await session.flush()
            await _process_pause_reminders(self.bot, session, self.now)
            self.assertEqual(self.bot.send_message.await_count, 0)

    async def test_observer_receives_no_regular_nudge_before_90_days(self) -> None:
        async with self.sessions() as session:
            user = await self._user(session, 7003)
            session.add(
                ParticipationLifecycle(
                    user_id=user.id,
                    participation_mode="OBSERVER",
                    activity_state="DORMANT",
                    state_since=self.now - timedelta(days=60),
                    mode_changed_at=self.now - timedelta(days=89),
                    onboarding_version=1,
                )
            )
            await session.flush()
            await _process_observer_checkins(self.bot, session, self.now)
            self.assertEqual(self.bot.send_message.await_count, 0)

    async def test_observer_checkin_is_at_most_once_per_90_day_period(self) -> None:
        async with self.sessions() as session:
            user = await self._user(session, 7004)
            session.add(
                ParticipationLifecycle(
                    user_id=user.id,
                    participation_mode="OBSERVER",
                    activity_state="DORMANT",
                    state_since=self.now - timedelta(days=120),
                    mode_changed_at=self.now - timedelta(days=91),
                    onboarding_version=1,
                )
            )
            await session.flush()

            await _process_observer_checkins(self.bot, session, self.now)
            await _process_observer_checkins(self.bot, session, self.now + timedelta(days=20))

            self.assertEqual(self.bot.send_message.await_count, 1)
            deliveries = int(
                await session.scalar(
                    select(func.count()).select_from(ParticipationModeDelivery).where(
                        ParticipationModeDelivery.user_id == user.id,
                        ParticipationModeDelivery.kind == "observer_checkin",
                    )
                )
                or 0
            )
            self.assertEqual(deliveries, 1)


if __name__ == "__main__":
    unittest.main()
