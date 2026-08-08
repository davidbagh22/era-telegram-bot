from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session
from app.api.v1.router import api_router


def _participant(**overrides) -> SimpleNamespace:
    defaults = dict(id=2, telegram_id=777, role="participant", is_blocked=False, is_archived=False)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _survey(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, title="Опрос", description="d", status="active")
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(user, session: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    return app


class ParticipantSurveysApiTests(unittest.TestCase):
    def test_list_surveys(self) -> None:
        survey = _survey()
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.surveys.survey_service.list_visible_surveys",
                new=AsyncMock(return_value=[survey]),
            ),
            patch(
                "app.api.v1.surveys.survey_service.get_response", new=AsyncMock(return_value=None)
            ),
            patch(
                "app.api.v1.surveys.survey_service.survey_questions", return_value=["Q1", "Q2"]
            ),
        ):
            response = client.get("/api/v1/surveys")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body[0]["title"], "Опрос")
        self.assertFalse(body[0]["completed"])

    def test_read_survey_not_found_when_draft(self) -> None:
        survey = _survey(status="draft")
        session = SimpleNamespace(get=AsyncMock(return_value=survey))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/surveys/1")
        self.assertEqual(response.status_code, 404)

    def test_read_survey_not_found_when_missing(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/surveys/999")
        self.assertEqual(response.status_code, 404)

    def test_submit_requires_answer_for_every_question(self) -> None:
        survey = _survey()
        session = SimpleNamespace(get=AsyncMock(return_value=survey))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.surveys.survey_service.survey_questions", return_value=["Q1", "Q2"]
        ):
            response = client.post("/api/v1/surveys/1/submit", json={"answers": ["Только один"]})
        self.assertEqual(response.status_code, 422)

    def test_submit_rejects_blank_answer(self) -> None:
        survey = _survey()
        session = SimpleNamespace(get=AsyncMock(return_value=survey))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.surveys.survey_service.survey_questions", return_value=["Q1", "Q2"]
        ):
            response = client.post("/api/v1/surveys/1/submit", json={"answers": ["Ответ", "   "]})
        self.assertEqual(response.status_code, 422)

    def test_submit_success(self) -> None:
        survey = _survey()
        session = SimpleNamespace(get=AsyncMock(return_value=survey))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.surveys.survey_service.survey_questions", return_value=["Q1", "Q2"]
            ),
            patch("app.api.v1.surveys.survey_service.submit_survey", new=AsyncMock()),
            patch(
                "app.api.v1.surveys.survey_service.get_response", new=AsyncMock(return_value=None)
            ),
        ):
            response = client.post(
                "/api/v1/surveys/1/submit", json={"answers": ["Ответ 1", "Ответ 2"]}
            )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
