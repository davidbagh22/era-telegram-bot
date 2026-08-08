from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, telegram_id=555, role="admin", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _participant(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=2, telegram_id=777, role="participant", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _survey(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1,
        title="Опрос",
        description="d",
        status="draft",
        is_monthly=False,
        sent_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(user, session: SimpleNamespace, bot=None) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    app.dependency_overrides[get_bot] = lambda: bot
    return app


class AdminSurveysApiTests(unittest.TestCase):
    def test_participant_forbidden(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/surveys")
        self.assertEqual(response.status_code, 403)

    def test_list_surveys(self) -> None:
        survey = _survey()
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.survey_admin_service.list_surveys", new=AsyncMock(return_value=[survey])
            ),
            patch(
                "app.api.v1.admin.survey_admin_service.response_count", new=AsyncMock(return_value=3)
            ),
            patch(
                "app.api.v1.admin.survey_service.survey_questions", return_value=["Q1", "Q2"]
            ),
        ):
            response = client.get("/api/v1/admin/surveys")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body[0]["title"], "Опрос")
        self.assertEqual(body[0]["response_count"], 3)

    def test_create_survey_requires_title(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/surveys", json={"title": "   ", "questions": ["Q1"]}
        )
        self.assertEqual(response.status_code, 422)

    def test_create_survey_requires_questions(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/surveys", json={"title": "T", "questions": ["   "]}
        )
        self.assertEqual(response.status_code, 422)

    def test_create_survey_success(self) -> None:
        survey = _survey()
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.survey_admin_service.create_survey", new=AsyncMock(return_value=survey)
            ),
            patch(
                "app.api.v1.admin.survey_admin_service.response_count", new=AsyncMock(return_value=0)
            ),
            patch(
                "app.api.v1.admin.survey_service.survey_questions", return_value=["Q1"]
            ),
        ):
            response = client.post(
                "/api/v1/admin/surveys", json={"title": "T", "questions": ["Q1"]}
            )
        self.assertEqual(response.status_code, 200)

    def test_update_survey_success(self) -> None:
        survey = _survey()
        session = SimpleNamespace(get=AsyncMock(return_value=survey))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch("app.api.v1.admin.survey_admin_service.update_survey", new=MagicMock()) as update_mock,
            patch(
                "app.api.v1.admin.survey_admin_service.response_count", new=AsyncMock(return_value=0)
            ),
            patch(
                "app.api.v1.admin.survey_service.survey_questions", return_value=["Q1", "Q2"]
            ),
        ):
            response = client.post(
                "/api/v1/admin/surveys/1/edit", json={"title": "New", "questions": ["Q1", "Q2"]}
            )
        self.assertEqual(response.status_code, 200)
        update_mock.assert_called_once()

    def test_survey_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/surveys/999/archive")
        self.assertEqual(response.status_code, 404)

    def test_archive_survey_success(self) -> None:
        survey = _survey()
        session = SimpleNamespace(get=AsyncMock(return_value=survey))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch("app.api.v1.admin.survey_admin_service.archive_survey", new=MagicMock()),
            patch(
                "app.api.v1.admin.survey_admin_service.response_count", new=AsyncMock(return_value=0)
            ),
            patch(
                "app.api.v1.admin.survey_service.survey_questions", return_value=["Q1"]
            ),
        ):
            response = client.post("/api/v1/admin/surveys/1/archive")
        self.assertEqual(response.status_code, 200)

    def test_send_survey_rejects_archived(self) -> None:
        survey = _survey(status="archived")
        session = SimpleNamespace(get=AsyncMock(return_value=survey))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/surveys/1/send")
        self.assertEqual(response.status_code, 409)

    def test_send_survey_requires_questions(self) -> None:
        survey = _survey(status="draft")
        session = SimpleNamespace(get=AsyncMock(return_value=survey))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch("app.api.v1.admin.survey_service.survey_questions", return_value=[]):
            response = client.post("/api/v1/admin/surveys/1/send")
        self.assertEqual(response.status_code, 422)

    def test_send_survey_success_broadcasts_and_marks_sent(self) -> None:
        survey = _survey(status="draft")
        recipient = SimpleNamespace(telegram_id=999)
        session = SimpleNamespace(get=AsyncMock(return_value=survey))
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        with (
            patch("app.api.v1.admin.survey_service.survey_questions", return_value=["Q1"]),
            patch(
                "app.api.v1.admin.survey_admin_service.send_recipients",
                new=AsyncMock(return_value=[recipient]),
            ),
            patch("app.api.v1.admin.broadcast_detailed", new=AsyncMock()) as broadcast_mock,
            patch("app.api.v1.admin.survey_admin_service.mark_sent", new=MagicMock()) as mark_sent_mock,
            patch(
                "app.api.v1.admin.survey_admin_service.response_count", new=AsyncMock(return_value=0)
            ),
        ):
            response = client.post("/api/v1/admin/surveys/1/send")
        self.assertEqual(response.status_code, 200)
        broadcast_mock.assert_awaited_once()
        mark_sent_mock.assert_called_once()

    def test_list_responses(self) -> None:
        survey = _survey()
        respondent = SimpleNamespace(id=2, first_name="Анна", last_name="ЭРА")
        response_row = SimpleNamespace(submitted_at=datetime.now(timezone.utc))
        session = SimpleNamespace(get=AsyncMock(return_value=survey))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.survey_admin_service.list_responses",
                new=AsyncMock(return_value=[(response_row, respondent)]),
            ),
            patch(
                "app.api.v1.admin.survey_service.answer_items",
                return_value=[{"question": "Q1", "answer": "A1"}],
            ),
        ):
            response = client.get("/api/v1/admin/surveys/1/responses")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body[0]["user_name"], "Анна ЭРА")
        self.assertEqual(body[0]["answers"][0]["answer"], "A1")


if __name__ == "__main__":
    unittest.main()
