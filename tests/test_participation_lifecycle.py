from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import PointTransaction, User
from app.database.participation_models import ReactivationCampaign
from app.services.participation_lifecycle_service import (
    MODE_OBSERVER,
    MODE_PAUSED,
    STATE_ACTIVE,
    STATE_ADAPTATION,
    STATE_COOLING,
    STATE_INACTIVE,
    ensure_reactivation_campaign,
    evaluate_activity_state,
    get_or_create_lifecycle,
    set_participation_mode,
)
from app.utils.constants import ApplicationStatus, PointCategory


class ParticipationLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _user(self, session, telegram_id: int, created_at: datetime) -> User:
        user = User(
            telegram_id=telegram_id,
            first_name="Test",
            application_status=ApplicationStatus.APPROVED,
        )
        session.add(user)
        await session.flush()
        user.created_at = created_at
        await session.flush()
        return user

    async def _point(self, session, user: User, source_type: str, at: datetime) -> None:
        session.add(
            PointTransaction(
                user_id=user.id,
                points=5,
                reason="test",
                category=PointCategory.OTHER,
                source_type=source_type,
                idempotency_key=f"{source_type}:{user.id}:{at.timestamp()}",
                created_at=at,
            )
        )
        await session.flush()

    async def test_new_member_stays_in_adaptation_without_activity(self) -> None:
        now = datetime(2026, 8, 19, 9, tzinfo=timezone.utc)
        async with self.sessions() as session:
            user = await self._user(session, 1001, now - timedelta(days=15))
            state, latest = await evaluate_activity_state(session, user, now=now)
            self.assertEqual(state, STATE_ADAPTATION)
            self.assertIsNone(latest)

    async def test_digital_points_do_not_make_active_base(self) -> None:
        now = datetime(2026, 8, 19, 9, tzinfo=timezone.utc)
        async with self.sessions() as session:
            user = await self._user(session, 1002, now - timedelta(days=40))
            await self._point(session, user, "digital_daily_open", now - timedelta(days=1))
            state, latest = await evaluate_activity_state(session, user, now=now)
            self.assertEqual(state, STATE_INACTIVE)
            self.assertIsNone(latest)

    async def test_verified_operational_action_makes_user_active(self) -> None:
        now = datetime(2026, 8, 19, 9, tzinfo=timezone.utc)
        async with self.sessions() as session:
            user = await self._user(session, 1003, now - timedelta(days=100))
            at = now - timedelta(days=10)
            await self._point(session, user, "task_completion", at)
            state, latest = await evaluate_activity_state(session, user, now=now)
            self.assertEqual(state, STATE_ACTIVE)
            self.assertEqual(latest, at)

    async def test_20_days_without_meaningful_action_is_cooling(self) -> None:
        now = datetime(2026, 8, 19, 9, tzinfo=timezone.utc)
        async with self.sessions() as session:
            user = await self._user(session, 1004, now - timedelta(days=100))
            at = now - timedelta(days=20)
            await self._point(session, user, "event_attendance", at)
            state, _ = await evaluate_activity_state(session, user, now=now)
            self.assertEqual(state, STATE_COOLING)

    async def test_pause_and_observer_stop_reactivation(self) -> None:
        now = datetime.now(timezone.utc)
        async with self.sessions() as session:
            user = await self._user(session, 1005, now - timedelta(days=100))
            lifecycle = await get_or_create_lifecycle(session, user)
            lifecycle.activity_state = STATE_COOLING
            lifecycle.state_since = now
            campaign = await ensure_reactivation_campaign(session, user, lifecycle, now=now)
            self.assertIsNotNone(campaign)
            await set_participation_mode(
                session,
                user,
                MODE_PAUSED,
                pause_until=(now + timedelta(days=30)).date(),
            )
            self.assertEqual(campaign.status, "paused")

            # A later active campaign also stops when the participant chooses observer.
            campaign2 = ReactivationCampaign(
                user_id=user.id,
                campaign_key=f"reactivation:{user.id}:second",
                status="active",
                current_attempt=0,
                started_at=now,
                next_attempt_at=now,
            )
            session.add(campaign2)
            await session.flush()
            await set_participation_mode(session, user, MODE_OBSERVER)
            self.assertEqual(campaign2.status, "completed")
            self.assertEqual(campaign2.outcome, "observer")


if __name__ == "__main__":
    unittest.main()
