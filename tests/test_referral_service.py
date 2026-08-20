from __future__ import annotations

import unittest
from datetime import date, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Event, PointTransaction, User
from app.database.referral_models import ReferralRelationship
from app.services.referral_service import (
    ACTIVE_REFERRAL_POINTS,
    FIRST_EVENT_REFERRAL_POINTS,
    REFERRAL_MONTHLY_CAP,
    REFERRAL_PER_INVITEE_CAP,
    REFERRAL_SOURCE_TYPES,
    REGISTRATION_REFERRAL_POINTS,
    award_active_referral,
    award_first_event_referral,
    award_registration_referral,
    bind_referral_code,
    get_or_create_referral_code,
    normalize_referral_code,
)
from app.utils.constants import ApplicationStatus, EventStatus


class ReferralServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _user(self, session, telegram_id: int, *, approved: bool = True) -> User:
        user = User(
            telegram_id=telegram_id,
            first_name="User",
            last_name=str(telegram_id),
            phone=f"+374{telegram_id:08d}",
            city="Yerevan",
            education_work="University",
            occupation="Student",
            motivation="Grow",
            available_time="Evenings",
            desired_path="participant",
            personal_data_consent=True,
            is_channel_subscribed=True,
            application_status=(
                ApplicationStatus.APPROVED if approved else ApplicationStatus.PENDING
            ),
        )
        session.add(user)
        await session.flush()
        return user

    async def _event(self, session, creator_id: int) -> Event:
        event = Event(
            title="ERA Meetup",
            description="Test",
            event_date=date.today(),
            event_time=time(18, 0),
            location="Yerevan",
            format="offline",
            status=EventStatus.COMPLETED,
            created_by=creator_id,
        )
        session.add(event)
        await session.flush()
        return event

    async def _referral_total(self, session, user_id: int) -> int:
        return int(
            await session.scalar(
                select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                    PointTransaction.user_id == user_id,
                    PointTransaction.source_type.in_(REFERRAL_SOURCE_TYPES),
                )
            )
            or 0
        )

    async def test_code_is_six_digits_and_cannot_self_refer(self) -> None:
        async with self.session_factory() as session:
            inviter = await self._user(session, 100001)
            code = await get_or_create_referral_code(session, inviter.id)
            self.assertEqual(len(code.code), 6)
            self.assertTrue(code.code.isdigit())
            self.assertEqual(normalize_referral_code(f" {code.code} "), code.code)
            self.assertIsNone(normalize_referral_code("12345"))

            with self.assertRaisesRegex(ValueError, "self_referral_not_allowed"):
                await bind_referral_code(session, invitee=inviter, value=code.code)

    async def test_rewards_are_inviter_only_ordered_and_idempotent(self) -> None:
        async with self.session_factory() as session:
            inviter = await self._user(session, 100001)
            invitee = await self._user(session, 100002, approved=False)
            code = await get_or_create_referral_code(session, inviter.id)
            relationship = await bind_referral_code(
                session,
                invitee=invitee,
                value=code.code,
            )
            self.assertIsNotNone(relationship)

            # Entering a code alone never creates points, and activity cannot
            # skip the approved-registration stage.
            self.assertEqual(int(await session.scalar(select(func.count(PointTransaction.id))) or 0), 0)
            event = await self._event(session, inviter.id)
            await award_first_event_referral(
                session,
                invitee_user_id=invitee.id,
                event_id=event.id,
            )
            self.assertEqual(int(await session.scalar(select(func.count(PointTransaction.id))) or 0), 0)

            invitee.application_status = ApplicationStatus.APPROVED
            await award_registration_referral(session, invitee_user_id=invitee.id)
            await award_registration_referral(session, invitee_user_id=invitee.id)

            registration_points = (
                await session.execute(
                    select(PointTransaction.user_id, PointTransaction.points).where(
                        PointTransaction.source_type == "referral_registration"
                    )
                )
            ).all()
            self.assertEqual(
                registration_points,
                [(inviter.id, REGISTRATION_REFERRAL_POINTS)],
            )

            await award_first_event_referral(
                session,
                invitee_user_id=invitee.id,
                event_id=event.id,
            )
            await award_first_event_referral(
                session,
                invitee_user_id=invitee.id,
                event_id=event.id,
            )
            activity_points = (
                await session.execute(
                    select(PointTransaction.user_id, PointTransaction.points).where(
                        PointTransaction.source_type == "referral_first_activity"
                    )
                )
            ).all()
            self.assertEqual(
                activity_points,
                [(inviter.id, FIRST_EVENT_REFERRAL_POINTS)],
            )

            # Economy v2 has no third reward stage and never rewards the invitee.
            await award_active_referral(session, invitee_user_id=invitee.id)
            await award_active_referral(session, invitee_user_id=invitee.id)
            active_points = int(
                await session.scalar(
                    select(func.count(PointTransaction.id)).where(
                        PointTransaction.source_type == "referral_active"
                    )
                )
                or 0
            )
            self.assertEqual(ACTIVE_REFERRAL_POINTS, 0)
            self.assertEqual(active_points, 0)
            self.assertEqual(await self._referral_total(session, inviter.id), REFERRAL_PER_INVITEE_CAP)
            self.assertEqual(await self._referral_total(session, invitee.id), 0)

            stored = await session.scalar(
                select(ReferralRelationship).where(
                    ReferralRelationship.invitee_id == invitee.id
                )
            )
            self.assertIsNotNone(stored.registration_rewarded_at)
            self.assertIsNotNone(stored.first_event_rewarded_at)
            self.assertEqual(stored.first_event_id, event.id)

    async def test_no_monthly_ceiling_but_each_invitee_is_capped_at_100(self) -> None:
        async with self.session_factory() as session:
            inviter = await self._user(session, 200001)
            code = await get_or_create_referral_code(session, inviter.id)
            event = await self._event(session, inviter.id)
            invitees: list[User] = []

            for offset in range(4):
                invitee = await self._user(session, 200010 + offset)
                invitees.append(invitee)
                await bind_referral_code(session, invitee=invitee, value=code.code)
                await award_registration_referral(session, invitee_user_id=invitee.id)
                await award_first_event_referral(
                    session,
                    invitee_user_id=invitee.id,
                    event_id=event.id,
                )

            # Zero means "no additional monthly ceiling". Four independent
            # conversions can therefore earn 4 × the per-invitee hard cap.
            self.assertEqual(REFERRAL_MONTHLY_CAP, 0)
            self.assertEqual(
                await self._referral_total(session, inviter.id),
                4 * REFERRAL_PER_INVITEE_CAP,
            )
            for invitee in invitees:
                self.assertEqual(await self._referral_total(session, invitee.id), 0)

            # Repeating stages for an already rewarded invitee stays idempotent.
            await award_registration_referral(session, invitee_user_id=invitees[-1].id)
            await award_first_event_referral(
                session,
                invitee_user_id=invitees[-1].id,
                event_id=event.id,
            )
            self.assertEqual(
                await self._referral_total(session, inviter.id),
                4 * REFERRAL_PER_INVITEE_CAP,
            )