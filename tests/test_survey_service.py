from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.management_models import AdminSurvey
from app.database.models import User
from app.services import survey_service as svc


class SurveyServiceParticipantTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def _survey(self, **overrides) -> AdminSurvey:
        defaults = dict(
            title="Пульс ЭРА",
            description="Тест",
            questions_json=svc.questions_payload(["Что работает?", "Что улучшить?"]),
            audience_type="approved",
            audience_filter_json={},
            status="active",
            is_monthly=False,
        )
        defaults.update(overrides)
        return AdminSurvey(**defaults)

    async def test_list_visible_surveys_excludes_draft_and_archived(self) -> None:
        async with self.session_factory() as session:
            session.add(self._survey(status="active"))
            session.add(self._survey(status="sent", title="Отправленный"))
            session.add(self._survey(status="draft", title="Черновик"))
            session.add(self._survey(status="archived", title="Архив"))
            await session.flush()

            visible = await svc.list_visible_surveys(session)
            titles = {survey.title for survey in visible}
            self.assertEqual(titles, {"Пульс ЭРА", "Отправленный"})

    async def test_get_response_returns_none_when_not_submitted(self) -> None:
        async with self.session_factory() as session:
            survey = self._survey()
            session.add(survey)
            user = User(telegram_id=1, first_name="U")
            session.add(user)
            await session.flush()

            response = await svc.get_response(session, survey.id, user.id)
            self.assertIsNone(response)

    async def test_submit_survey_creates_response(self) -> None:
        async with self.session_factory() as session:
            survey = self._survey()
            session.add(survey)
            user = User(telegram_id=1, first_name="U")
            session.add(user)
            await session.flush()

            response = await svc.submit_survey(session, survey, user, ["Ответ 1", "Ответ 2"])
            self.assertEqual(response.status, "completed")
            self.assertEqual(
                response.answers_json,
                [
                    {"question": "Что работает?", "answer": "Ответ 1"},
                    {"question": "Что улучшить?", "answer": "Ответ 2"},
                ],
            )

    async def test_submit_survey_upserts_single_response_per_user(self) -> None:
        async with self.session_factory() as session:
            survey = self._survey()
            session.add(survey)
            user = User(telegram_id=1, first_name="U")
            session.add(user)
            await session.flush()

            await svc.submit_survey(session, survey, user, ["Первый", "Второй"])
            second = await svc.submit_survey(session, survey, user, ["Обновлённый", "Ответ"])

            response = await svc.get_response(session, survey.id, user.id)
            self.assertEqual(response.id, second.id)
            self.assertEqual(response.answers_json[0]["answer"], "Обновлённый")


if __name__ == "__main__":
    unittest.main()
