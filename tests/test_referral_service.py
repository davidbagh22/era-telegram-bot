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
    REGISTRATION_REFERRAL_POINTS,
    award_active_referral,
    award_first_event_referral,
    award_registration_referral,
    bind_referral_code,
    get_or_create_referral_code,
    normalize_referral_code,
)
from app.utils.constants import ApplicationStatus, EventStatus, ParticipationStatus


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

    async def test_rewards_are_ordered_idempotent_and_total_250(self) -> None:
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

            # Even an event cannot skip the approved registration stage.
            event = await self._event(session, inviter.id)
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

            # The third stage is driven by the real participation status.
            await award_active_referral(session, invitee_user_id=invitee.id)
            no_active_points = int(
                await session.scalar(
                    select(func.count(PointTransaction.id)).where(
                        PointTransaction.source_type == "referral_active"
                    )
                )
                or 0
            )
            self.assertEqual(no_active_points, 0)

            invitee.participation_status = ParticipationStatus.ACTIVE_MEMBER
            await award_active_referral(session, invitee_user_id=invitee.id)
            await award_active_referral(session, invitee_user_id=invitee.id)

            active_points = (
                await session.execute(
                    select(PointTransaction.user_id, PointTransaction.points).where(
                        PointTransaction.source_type == "referral_active"
                    )
                )
            ).all()
            self.assertCountEqual(
                active_points,
                [
                    (inviter.id, ACTIVE_REFERRAL_POINTS),
                    (invitee.id, ACTIVE_REFERRAL_POINTS),
                ],
            )

            inviter_total = int(
                await session.scalar(
                    select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                        PointTransaction.user_id == inviter.id,
                        PointTransaction.source_type.in_(
                            (
                                "referral_registration",
                                "referral_first_event",
                                "referral_active",
                            )
                        ),
                    )
                )
                or 0
            )
            invitee_total = int(
                await session.scalar(
                    select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                        PointTransaction.user_id == invitee.id,
                        PointTransaction.source_type.in_(
                            (
                                "referral_registration",
                                "referral_first_event",
                                "referral_active",
                            )
                        ),
                    )
                )
                or 0
            )
            self.assertEqual(
                REGISTRATION_REFERRAL_POINTS
                + FIRST_EVENT_REFERRAL_POINTS
                + ACTIVE_REFERRAL_POINTS,
                REFERRAL_PER_INVITEE_CAP,
            )
            self.assertEqual(inviter_total, REFERRAL_PER_INVITEE_CAP)
            self.assertEqual(invitee_total, REFERRAL_PER_INVITEE_CAP)

            stored = await session.scalar(
                select(ReferralRelationship).where(
                    ReferralRelationship.invitee_id == invitee.id
                )
            )
            self.assertIsNotNone(stored.registration_rewarded_at)
            self.assertIsNotNone(stored.first_event_rewarded_at)
            self.assertEqual(stored.first_event_id, event.id)

    async def test_inviter_referral_points_are_capped_at_750_per_month(self) -> None:
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
                invitee.participation_status = ParticipationStatus.ACTIVE_MEMBER
                await award_active_referral(session, invitee_user_id=invitee.id)

            inviter_total = int(
                await session.scalar(
                    select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                        PointTransaction.user_id == inviter.id,
                        PointTransaction.source_type.in_(
                            (
                                "referral_registration",
                                "referral_first_event",
                                "referral_active",
                            )
                        ),
                    )
                )
                or 0
            )
            self.assertEqual(inviter_total, REFERRAL_MONTHLY_CAP)

            # Cap applies to the inviter's referral earnings. Existing product
            # semantics keep each invited participant's own stage bonuses full.
            fourth_invitee_total = int(
                await session.scalar(
                    select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                        PointTransaction.user_id == invitees[-1].id,
                        PointTransaction.source_type.in_(
                            (
                                "referral_registration",
                                "referral_first_event",
                                "referral_active",
                            )
                        ),
                    )
                )
                or 0
            )
            self.assertEqual(fourth_invitee_total, REFERRAL_PER_INVITEE_CAP)

            # Repeating any stage after the cap is exhausted stays idempotent.
            await award_registration_referral(session, invitee_user_id=invitees[-1].id)
            await award_first_event_referral(
                session,
                invitee_user_id=invitees[-1].id,
                event_id=event.id,
            )
            await award_active_referral(session, invitee_user_id=invitees[-1].id)
            inviter_total_after_repeat = int(
                await session.scalar(
                    select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                        PointTransaction.user_id == inviter.id,
                        PointTransaction.source_type.in_(
                            (
                                "referral_registration",
                                "referral_first_event",
                                "referral_active",
                            )
                        ),
                    )
                )
                or 0
            )
            self.assertEqual(inviter_total_after_repeat, REFERRAL_MONTHLY_CAP)
