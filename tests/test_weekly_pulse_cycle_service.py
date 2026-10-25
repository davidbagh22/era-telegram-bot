from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import User
from app.services.weekly_pulse_cycle_service import (
    WeeklyPulseConfigurationError,
    create_or_get_cycle,
    eligible_members,
    update_schedule,
    upsert_leader_membership,
    validate_schedule_values,
)
from app.utils.constants import ApplicationStatus, Role


class WeeklyPulseCycleServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def test_schedule_validation_requires_reminders_before_deadline(self) -> None:
        with self.assertRaisesRegex(WeeklyPulseConfigurationError, "reminders_must_be_ordered"):
            validate_schedule_values(
                open_weekday=0,
                open_time=time(18),
                deadline_hours=24,
                first_reminder_hours=24,
                final_reminder_hours=4,
                report_weekday=6,
                timezone_name="Asia/Yerevan",
            )

    async def test_cycle_is_idempotent_and_uses_configured_window(self) -> None:
        async with self.factory() as session:
            await update_schedule(
                session,
                enabled=True,
                open_weekday=0,
                open_time=time(9),
                deadline_hours=36,
                first_reminder_hours=24,
                final_reminder_hours=4,
                report_weekday=6,
                timezone_name="UTC",
            )
            first = await create_or_get_cycle(
                session,
                date_from=date(2026, 10, 5),
                date_to=date(2026, 10, 11),
                leader_chat_id=-100123,
            )
            again = await create_or_get_cycle(
                session,
                date_from=date(2026, 10, 5),
                date_to=date(2026, 10, 11),
                leader_chat_id=-100123,
            )
            self.assertEqual(first.id, again.id)
            self.assertEqual(first.opens_at.hour, 9)
            self.assertEqual(first.deadline_at - first.opens_at, timedelta(hours=36))

    async def test_roster_eligibility_tracks_chat_membership_without_changing_role(self) -> None:
        async with self.factory() as session:
            user = User(
                telegram_id=501,
                first_name="Ari",
                role=Role.PARTICIPANT,
                application_status=ApplicationStatus.APPROVED,
            )
            session.add(user)
            await session.flush()
            stamp = datetime(2026, 10, 3, tzinfo=timezone.utc)
            row = await upsert_leader_membership(
                session,
                leader_chat_id=-100123,
                telegram_user_id=501,
                membership_status="member",
                display_name="Ari A",
                now=stamp,
            )
            self.assertEqual(row.user_id, user.id)
            self.assertEqual(user.role, Role.PARTICIPANT)
            await upsert_leader_membership(
                session,
                leader_chat_id=-100123,
                telegram_user_id=501,
                membership_status="left",
                display_name="Ari A",
                now=stamp,
            )
            self.assertEqual(await eligible_members(session, leader_chat_id=-100123), [])
