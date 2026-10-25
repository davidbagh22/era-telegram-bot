from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import ActivityMetric, PointTransaction, User
from app.database.partners import Partner, PartnerInitiative
from app.services.home_service import _earned_points_periods, _recognition_progress
from app.utils.constants import ParticipationStatus


class HomeProgressDefinitionOfDoneTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _user(self, session, telegram_id: int, *, status: str) -> User:
        user = User(
            telegram_id=telegram_id,
            first_name="Home",
            last_name="Test",
            phone=f"+374{telegram_id:08d}",
            city="Yerevan",
            education_work="University",
            occupation="Student",
            motivation="Grow",
            available_time="Evenings",
            desired_path="participant",
            personal_data_consent=True,
            is_channel_subscribed=True,
            participation_status=status,
        )
        session.add(user)
        await session.flush()
        return user

    async def test_today_and_month_earned_points_use_yerevan_boundaries_and_ignore_spending(self) -> None:
        async with self.session_factory() as session:
            user = await self._user(
                session,
                310001,
                status=ParticipationStatus.ACTIVE_MEMBER,
            )
            # 2026-08-02 00:30 in Yerevan. Day boundary is 20:00 UTC;
            # month boundary is 2026-07-31 20:00 UTC.
            now = datetime(2026, 8, 1, 20, 30, tzinfo=timezone.utc)
            session.add_all(
                [
                    PointTransaction(
                        user_id=user.id,
                        points=5,
                        reason="today",
                        created_at=datetime(2026, 8, 1, 20, 15, tzinfo=timezone.utc),
                    ),
                    PointTransaction(
                        user_id=user.id,
                        points=20,
                        reason="month earlier day",
                        created_at=datetime(2026, 8, 1, 19, 30, tzinfo=timezone.utc),
                    ),
                    PointTransaction(
                        user_id=user.id,
                        points=30,
                        reason="previous month",
                        created_at=datetime(2026, 7, 31, 19, 0, tzinfo=timezone.utc),
                    ),
                    PointTransaction(
                        user_id=user.id,
                        points=-10,
                        reason="spending is not earnings",
                        created_at=datetime(2026, 8, 1, 20, 20, tzinfo=timezone.utc),
                    ),
                ]
            )
            await session.flush()

            today, month = await _earned_points_periods(session, user.id, now=now)

            self.assertEqual(today, 5)
            self.assertEqual(month, 25)

    async def test_single_missing_requirement_is_almost_with_truthful_points_gap(self) -> None:
        async with self.session_factory() as session:
            user = await self._user(
                session,
                310002,
                status=ParticipationStatus.ACTIVE_MEMBER,
            )
            session.add(
                PointTransaction(user_id=user.id, points=200, reason="earned")
            )
            session.add(ActivityMetric(user_id=user.id, metric_key="volunteer_hours", value=10))
            partner = Partner(name="ЭРА", description="d")
            session.add(partner)
            await session.flush()
            session.add(
                PartnerInitiative(
                    partner_id=partner.id,
                    title="Volunteer certificate",
                    description="d",
                    point_cost=300,
                    opportunity_type="certificate",
                    min_rank=ParticipationStatus.ACTIVE_MEMBER,
                    eligibility_json={"required_metrics": {"volunteer_hours": 10}},
                )
            )
            await session.flush()

            available, almost, locked = await _recognition_progress(session, user)

            self.assertIsNone(available)
            self.assertIsNotNone(almost)
            self.assertIsNone(locked)
            self.assertEqual(almost.display_state, "almost")
            self.assertEqual(almost.points_needed, 100)
            self.assertEqual(almost.progress_text, "осталось 100 баллов")

    async def test_multiple_missing_requirements_never_collapse_to_zero_points(self) -> None:
        async with self.session_factory() as session:
            user = await self._user(
                session,
                310003,
                status=ParticipationStatus.NEW_MEMBER,
            )
            session.add(PointTransaction(user_id=user.id, points=400, reason="earned"))
            session.add(ActivityMetric(user_id=user.id, metric_key="volunteer_hours", value=2))
            partner = Partner(name="КСООРС Армении", description="d")
            session.add(partner)
            await session.flush()
            session.add(
                PartnerInitiative(
                    partner_id=partner.id,
                    title="Volunteer recognition",
                    description="d",
                    point_cost=300,
                    opportunity_type="certificate",
                    min_rank=ParticipationStatus.TEAM_MEMBER,
                    eligibility_json={"required_metrics": {"volunteer_hours": 20}},
                )
            )
            await session.flush()

            available, almost, locked = await _recognition_progress(session, user)

            self.assertIsNone(available)
            self.assertIsNone(almost)
            self.assertIsNotNone(locked)
            self.assertEqual(locked.display_state, "locked")
            self.assertIn("нужен ранг: Член команды", locked.progress_text)
            self.assertIn("ещё 18 часов волонтёрства", locked.progress_text)


if __name__ == "__main__":
    unittest.main()
