from __future__ import annotations

import unittest
from datetime import datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import AppSetting, PointTransaction, User
from app.services.digital_engagement_service import (
    IMPORTANT_MATERIALS_SETTING_KEY,
    award_material_acknowledgement,
    award_profile_completion,
    digital_points_this_month,
)
from app.utils.constants import ApplicationStatus, PointCategory


class DigitalEngagementRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _complete_user(self, session, telegram_id: int = 1) -> User:
        user = User(
            telegram_id=telegram_id,
            first_name="David",
            last_name="Test",
            birth_date=datetime(2002, 5, 22).date(),
            phone="+37400000000",
            email="test@example.com",
            city="Yerevan",
            education_work="University",
            occupation="Student",
            skills=["projects"],
            experience="Experience",
            motivation="Motivation",
            application_status=ApplicationStatus.APPROVED,
        )
        session.add(user)
        await session.flush()
        return user

    async def test_profile_completion_is_50_and_idempotent(self) -> None:
        async with self.sessions() as session:
            user = await self._complete_user(session)
            first = await award_profile_completion(session, user)
            second = await award_profile_completion(session, user)
            self.assertIsNotNone(first)
            self.assertEqual(first.points, 50)
            self.assertEqual(first.id, second.id)
            self.assertEqual(await digital_points_this_month(session, user.id), 50)

    async def test_material_ack_is_allowlisted_once_and_max_five_per_month(self) -> None:
        async with self.sessions() as session:
            user = await self._complete_user(session, telegram_id=2)
            session.add(
                AppSetting(
                    key=IMPORTANT_MATERIALS_SETTING_KEY,
                    value=[
                        {"key": f"m{i}", "version": "v1", "title": f"Material {i}"}
                        for i in range(1, 7)
                    ],
                )
            )
            await session.flush()
            first = await award_material_acknowledgement(
                session, user, material_key="m1", material_version="v1"
            )
            retry = await award_material_acknowledgement(
                session, user, material_key="m1", material_version="v1"
            )
            self.assertEqual(first.id, retry.id)
            for i in range(2, 6):
                self.assertIsNotNone(
                    await award_material_acknowledgement(
                        session, user, material_key=f"m{i}", material_version="v1"
                    )
                )
            self.assertIsNone(
                await award_material_acknowledgement(
                    session, user, material_key="m6", material_version="v1"
                )
            )
            self.assertEqual(await digital_points_this_month(session, user.id), 25)

    async def test_global_cap_never_exceeds_300(self) -> None:
        async with self.sessions() as session:
            user = await self._complete_user(session, telegram_id=3)
            now = datetime.now().astimezone()
            session.add(
                PointTransaction(
                    user_id=user.id,
                    points=295,
                    reason="existing digital",
                    category=PointCategory.DIGITAL_ENGAGEMENT,
                    source_type="digital_existing",
                    idempotency_key="digital:existing:295",
                    created_at=now,
                )
            )
            session.add(
                AppSetting(
                    key=IMPORTANT_MATERIALS_SETTING_KEY,
                    value=[{"key": "final", "version": "v1", "title": "Final"}],
                )
            )
            await session.flush()
            award = await award_material_acknowledgement(
                session, user, material_key="final", material_version="v1"
            )
            self.assertIsNotNone(award)
            self.assertEqual(award.points, 5)
            self.assertEqual(await digital_points_this_month(session, user.id), 300)


if __name__ == "__main__":
    unittest.main()
