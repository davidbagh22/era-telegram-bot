from __future__ import annotations

import unittest
from datetime import date, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import Event, PointTransaction, User
from app.database.referral_models import ReferralRelationship
from app.services.referral_service import (
    FIRST_EVENT_REFERRAL_POINTS,
    REGISTRATION_REFERRAL_POINTS,
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

    async def test_rewards_are_ordered_and_idempotent(self) -> None:
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

            # Entering a code alone never creates points.
            before = await session.scalar(select(func.count(PointTransaction.id)))
            self.assertEqual(int(before or 0), 0)

            # Even an event cannot skip the approved registration + chat stage.
            event = Event(
                title="ERA Meetup",
                description="Test",
                event_date=date.today(),
                event_time=time(18, 0),
                location="Yerevan",
                format="offline",
                status=EventStatus.COMPLETED,
                created_by=inviter.id,
            )
            session.add(event)
            await session.flush()
            await award_first_event_referral(
                session,
                invitee_user_id=invitee.id,
                event_id=event.id,
            )
            self.assertEqual(
                int(await session.scalar(select(func.count(PointTransaction.id))) or 0),
                0,
            )

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
            self.assertCountEqual(
                registration_points,
                [
                    (inviter.id, REGISTRATION_REFERRAL_POINTS),
                    (invitee.id, REGISTRATION_REFERRAL_POINTS),
                ],
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
            event_points = (
                await session.execute(
                    select(PointTransaction.user_id, PointTransaction.points).where(
                        PointTransaction.source_type == "referral_first_event"
                    )
                )
            ).all()
            self.assertCountEqual(
                event_points,
                [
                    (inviter.id, FIRST_EVENT_REFERRAL_POINTS),
                    (invitee.id, FIRST_EVENT_REFERRAL_POINTS),
                ],
            )

            stored = await session.scalar(
                select(ReferralRelationship).where(
                    ReferralRelationship.invitee_id == invitee.id
                )
            )
            self.assertIsNotNone(stored.registration_rewarded_at)
            self.assertIsNotNone(stored.first_event_rewarded_at)
            self.assertEqual(stored.first_event_id, event.id)
