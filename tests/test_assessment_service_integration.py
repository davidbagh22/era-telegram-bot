from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.development_models import UserVectorProfile
from app.database.models import User
from app.services.assessment_service import (
    complete_assessment,
    ensure_catalog,
    save_answer,
    start_assessment,
)


class AssessmentServiceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_who5_can_be_started_resumed_completed_and_saved_to_profile(self) -> None:
        async with self.session_factory() as session:
            user = User(telegram_id=900001, first_name="Тест", age=20)
            session.add(user)
            await session.flush()

            await ensure_catalog(session)
            started = await start_assessment(session, user, "WHO5_RU")
            self.assertEqual(started["status"], "in_progress")
            self.assertEqual(started["question_count"], 5)

            resumed = await start_assessment(session, user, "WHO5_RU")
            self.assertEqual(resumed["id"], started["id"])

            current = started
            for question in started["questions"]:
                current = await save_answer(
                    session,
                    user.id,
                    started["id"],
                    question["code"],
                    5,
                )
            self.assertEqual(current["answered_count"], 5)

            result = await complete_assessment(session, user.id, started["id"])
            self.assertEqual(result["scores"]["wellbeing"]["raw"], 100.0)
            self.assertEqual(result["scores"]["wellbeing"]["normalized"], 100.0)

            profile = await session.get(UserVectorProfile, user.id)
            self.assertIsNotNone(profile)
            assert profile is not None
            self.assertEqual(profile.state_json["who5_wellbeing"], 100)
            self.assertIsNone(profile.current_index)

    async def test_big_five_updates_traits_but_never_vector_index(self) -> None:
        async with self.session_factory() as session:
            user = User(telegram_id=900002, first_name="Тест", age=20)
            session.add(user)
            await session.flush()

            await ensure_catalog(session)
            started = await start_assessment(session, user, "IPIP_BIG5_RU")
            self.assertEqual(started["question_count"], 50)
            for question in started["questions"]:
                await save_answer(session, user.id, started["id"], question["code"], 3)

            result = await complete_assessment(session, user.id, started["id"])
            self.assertEqual(set(result["scores"]), {
                "extraversion",
                "agreeableness",
                "conscientiousness",
                "emotional_stability",
                "intellect",
            })

            profile = await session.get(UserVectorProfile, user.id)
            self.assertIsNotNone(profile)
            assert profile is not None
            self.assertIn("big5", profile.traits_json)
            self.assertIsNone(profile.current_index)


if __name__ == "__main__":
    unittest.main()
