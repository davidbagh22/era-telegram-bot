from __future__ import annotations

import unittest
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.leadership_models import WeeklyPulseParticipant
from app.database.models import User
from app.services.weekly_pulse_cycle_service import (
    create_or_get_cycle,
    mark_cycle_participant_submitted,
    upsert_leader_membership,
)
from app.utils.constants import ApplicationStatus, Role


class PulseSubmissionCounterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_submission_updates_counter_immediately_and_is_idempotent(self):
        async with self.factory() as session:
            users = []
            for telegram_id in (71001, 71002):
                user = User(
                    telegram_id=telegram_id,
                    first_name=f"Leader {telegram_id}",
                    role=Role.PARTICIPANT,
                    application_status=ApplicationStatus.APPROVED,
                )
                session.add(user)
                users.append(user)
            await session.flush()
            cycle = await create_or_get_cycle(
                session,
                date_from=date(2026, 10, 26),
                date_to=date(2026, 11, 1),
                leader_chat_id=-100123,
            )
            for user in users:
                await upsert_leader_membership(
                    session,
                    leader_chat_id=-100123,
                    telegram_user_id=user.telegram_id,
                    membership_status="member",
                    display_name=user.first_name,
                )
                session.add(
                    WeeklyPulseParticipant(
                        cycle_id=cycle.id,
                        user_id=user.id,
                        telegram_user_id=user.telegram_id,
                        status="in_progress",
                    )
                )
            await session.flush()

            await mark_cycle_participant_submitted(session, cycle=cycle, user_id=users[0].id)
            self.assertEqual((cycle.submitted_count, cycle.eligible_count), (1, 2))

            await mark_cycle_participant_submitted(session, cycle=cycle, user_id=users[0].id)
            self.assertEqual((cycle.submitted_count, cycle.eligible_count), (1, 2))

            await mark_cycle_participant_submitted(session, cycle=cycle, user_id=users[1].id)
            self.assertEqual((cycle.submitted_count, cycle.eligible_count), (2, 2))

    async def test_unknown_user_does_not_create_participant(self):
        async with self.factory() as session:
            cycle = await create_or_get_cycle(
                session,
                date_from=date(2026, 10, 26),
                date_to=date(2026, 11, 1),
                leader_chat_id=-100123,
            )
            await mark_cycle_participant_submitted(session, cycle=cycle, user_id=99999)
            self.assertEqual(cycle.submitted_count, 0)
            self.assertEqual(cycle.eligible_count, 0)
