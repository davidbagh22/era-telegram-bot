from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import User
from app.services import survey_admin_service as svc
from app.services import survey_service
from app.utils.constants import ApplicationStatus


class SurveyAdminServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_create_survey_defaults_to_draft(self) -> None:
        async with self.session_factory() as session:
            survey = await svc.create_survey(
                session, title="Опрос", description=None, questions=["Q1", "Q2"], created_by_id=1
            )
            self.assertEqual(survey.status, "draft")
            self.assertFalse(survey.is_monthly)
            self.assertEqual(survey_service.survey_questions(survey), ["Q1", "Q2"])

    async def test_get_or_create_monthly_survey_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            first = await svc.get_or_create_monthly_survey(session, created_by_id=1)
            second = await svc.get_or_create_monthly_survey(session, created_by_id=1)
            self.assertEqual(first.id, second.id)
            self.assertTrue(first.is_monthly)

    async def test_update_survey_overwrites_fields(self) -> None:
        async with self.session_factory() as session:
            survey = await svc.create_survey(
                session, title="Old", description="old", questions=["Q1"], created_by_id=1
            )
            svc.update_survey(
                survey, title="New", description="new", questions=["Q1", "Q2"], updated_by_id=2
            )
            self.assertEqual(survey.title, "New")
            self.assertEqual(survey.updated_by, 2)
            self.assertEqual(survey_service.survey_questions(survey), ["Q1", "Q2"])

    async def test_archive_survey_sets_status(self) -> None:
        async with self.session_factory() as session:
            survey = await svc.create_survey(
                session, title="T", description=None, questions=["Q1"], created_by_id=1
            )
            svc.archive_survey(survey, updated_by_id=1)
            self.assertEqual(survey.status, "archived")

    async def test_send_recipients_excludes_blocked_archived_and_unapproved(self) -> None:
        async with self.session_factory() as session:
            approved = User(
                telegram_id=1,
                first_name="A",
                application_status=ApplicationStatus.APPROVED,
                is_blocked=False,
                is_archived=False,
            )
            blocked = User(
                telegram_id=2,
                first_name="B",
                application_status=ApplicationStatus.APPROVED,
                is_blocked=True,
                is_archived=False,
            )
            pending = User(
                telegram_id=3,
                first_name="C",
                application_status=ApplicationStatus.PENDING,
                is_blocked=False,
                is_archived=False,
            )
            session.add_all([approved, blocked, pending])
            await session.flush()

            recipients = await svc.send_recipients(session)
            self.assertEqual([u.id for u in recipients], [approved.id])

    async def test_mark_sent_sets_last_sent_month_for_monthly_survey(self) -> None:
        async with self.session_factory() as session:
            survey = await svc.get_or_create_monthly_survey(session, created_by_id=1)
            svc.mark_sent(survey, timezone_name="Asia/Yerevan", updated_by_id=1)
            self.assertEqual(survey.status, "sent")
            self.assertIsNotNone(survey.sent_at)
            self.assertIsNotNone(survey.last_sent_month)

    async def test_response_count_and_list_responses(self) -> None:
        async with self.session_factory() as session:
            survey = await svc.create_survey(
                session, title="T", description=None, questions=["Q1"], created_by_id=1
            )
            user = User(telegram_id=1, first_name="U")
            session.add(user)
            await session.flush()
            await survey_service.submit_survey(session, survey, user, ["Ответ"])

            count = await svc.response_count(session, survey.id)
            self.assertEqual(count, 1)

            rows = await svc.list_responses(session, survey.id)
            self.assertEqual(len(rows), 1)
            response, respondent = rows[0]
            self.assertEqual(respondent.id, user.id)
            self.assertEqual(response.answers_json[0]["answer"], "Ответ")


if __name__ == "__main__":
    unittest.main()
