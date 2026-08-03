from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.services.portfolio_service import PortfolioData, PortfolioEntry
from app.utils.constants import ParticipationStatus


def _user(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1,
        telegram_id=555,
        first_name="Мария",
        last_name="И.",
        role="participant",
        participation_status=ParticipationStatus.ACTIVE_MEMBER,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _portfolio() -> PortfolioData:
    return PortfolioData(
        full_name="Мария И.",
        role="participant",
        participation_status="active_member",
        departments=["Внутренние связи"],
        directions=["Культура"],
        period="с 01.01.2026",
        city="Ереван",
        stats={"points": 120, "events": 3, "projects": 1, "completed_projects": 0, "tasks": 2, "portfolio": 1},
        projects=[PortfolioEntry(title="Квест", status="в работе")],
        badges=[PortfolioEntry(title="Первый шаг")],
    )


def _build_app(session: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_session] = _session_override
    return app


class ProfileApiTests(unittest.TestCase):
    def test_read_profile_combines_identity_growth_and_portfolio(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        with patch(
            "app.api.v1.profile.build_portfolio_data", new=AsyncMock(return_value=_portfolio())
        ):
            response = client.get("/api/v1/profile")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["first_name"], "Мария")
        self.assertEqual(body["growth"]["level"], "active")
        self.assertEqual(body["stats"]["points"], 120)
        self.assertEqual(body["projects"][0]["title"], "Квест")
        self.assertEqual(body["badges"][0]["title"], "Первый шаг")

    def test_read_profile_requires_auth(self) -> None:
        app = FastAPI()
        app.include_router(api_router)

        async def _session_override():
            yield SimpleNamespace()

        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
        client = TestClient(app)
        response = client.get("/api/v1/profile")
        self.assertEqual(response.status_code, 401)

    def test_resume_pdf_returns_pdf_content_type(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.profile.build_portfolio_data", new=AsyncMock(return_value=_portfolio())
            ),
            patch("app.api.v1.profile.build_era_resume", return_value=b"%PDF-fake"),
        ):
            response = client.get("/api/v1/profile/resume.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertEqual(response.content, b"%PDF-fake")


if __name__ == "__main__":
    unittest.main()
