from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.development_models import MonthlyCheckin, UserVectorProfile
from app.database.models import User
from app.services.development_service import vector_home_summary


class VectorHomeSummaryTests(unittest.IsolatedAsyncioTestCase):
    """DELTA ToR §2-5: Home's safe "Мой вектор" summary."""

    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int = 1) -> User:
        user = User(telegram_id=telegram_id, first_name="Dev")
        session.add(user)
        await session.flush()
        return user

    async def test_no_profile_yet_returns_none_not_fake_zero(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            self.assertIsNone(await vector_home_summary(session, user.id))

    async def test_profile_with_no_checkin_yet_returns_none(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            # A profile row can exist (e.g. created on registration) without
            # ever having a completed check-in -- current_index stays unset.
            session.add(UserVectorProfile(user_id=user.id, current_index=None, state_json={}))
            await session.flush()
            self.assertIsNone(await vector_home_summary(session, user.id))

    async def test_filled_profile_maps_areas_to_the_wire_contract_keys(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            now = datetime.now(timezone.utc)
            session.add(
                UserVectorProfile(
                    user_id=user.id,
                    current_index=74,
                    state_json={"energy": 67, "agency": 76, "autonomy": 71, "connection": 82, "direction": 74},
                    last_checkin_at=now,
                )
            )
            await session.flush()

            summary = await vector_home_summary(session, user.id)

            self.assertIsNotNone(summary)
            self.assertEqual(summary.pulse, 74)
            # "agency" (internal dimension code) must surface as "support"
            # (the ToR's literal JSON contract), not the internal name.
            self.assertEqual(
                summary.areas,
                {"energy": 67, "support": 76, "autonomy": 71, "connection": 82, "direction": 74},
            )
            self.assertNotIn("agency", summary.areas)

    async def test_never_leaks_answers_notes_or_goals(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            session.add(
                UserVectorProfile(
                    user_id=user.id,
                    current_index=50,
                    state_json={"energy": 50, "agency": 50, "autonomy": 50, "connection": 50, "direction": 50},
                    last_checkin_at=datetime.now(timezone.utc),
                )
            )
            await session.flush()

            summary = await vector_home_summary(session, user.id)

            fields = vars(summary)
            self.assertNotIn("answers", fields)
            self.assertNotIn("notes", fields)
            self.assertNotIn("goals", fields)
            self.assertEqual(set(fields.keys()), {"pulse", "updated_at", "areas", "signals"})

    async def test_signals_pick_the_largest_deltas_from_latest_completed_checkin(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            session.add(
                UserVectorProfile(
                    user_id=user.id,
                    current_index=70,
                    state_json={"energy": 67, "agency": 76, "autonomy": 71, "connection": 82, "direction": 74},
                    last_checkin_at=datetime.now(timezone.utc),
                )
            )
            session.add(
                MonthlyCheckin(
                    user_id=user.id,
                    month="2026-08",
                    status="completed",
                    state_json={"energy": 67, "agency": 76, "autonomy": 71, "connection": 82, "direction": 74},
                    delta_json={"energy": -10, "agency": 1, "autonomy": 0, "connection": 15, "direction": -2},
                )
            )
            await session.flush()

            summary = await vector_home_summary(session, user.id)

            self.assertEqual(len(summary.signals), 2)
            self.assertEqual(summary.signals[0].area, "connection")
            self.assertEqual(summary.signals[0].trend, "up")
            self.assertEqual(summary.signals[1].area, "energy")
            self.assertEqual(summary.signals[1].trend, "down")


if __name__ == "__main__":
    unittest.main()
