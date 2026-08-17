from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session
from app.api.v1.router import api_router
from app.services.position_management_service import PositionError


def _user(**overrides) -> SimpleNamespace:
    defaults = dict(id=2, telegram_id=777, role="participant", is_blocked=False, is_archived=False)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _office(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1,
        title="Лидер Медиа",
        description="d",
        is_active=True,
        is_public=True,
        application_enabled=True,
        application_deadline=None,
        requirements="req",
        default_term_days=180,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _application(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=10,
        office_id=1,
        user_id=2,
        status="submitted",
        motivation="m",
        plan=None,
        availability=None,
        submitted_at=None,
        review_note=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(user, session: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_current_user] = lambda: user

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    return app


class PositionsApiTests(unittest.TestCase):
    def test_read_open_positions(self) -> None:
        office = _office()
        session = SimpleNamespace()
        app = _build_app(_user(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.positions.position_management_service.list_open_positions",
                new=AsyncMock(return_value=[office]),
            ),
            patch(
                "app.api.v1.positions.position_management_service.application_count",
                new=AsyncMock(return_value=3),
            ),
        ):
            response = client.get("/api/v1/positions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["title"], "Лидер Медиа")
        self.assertEqual(response.json()[0]["application_count"], 3)

    def test_read_position_not_found_when_private(self) -> None:
        office = _office(is_public=False)
        session = SimpleNamespace(get=AsyncMock(return_value=office))
        app = _build_app(_user(), session)
        client = TestClient(app)
        response = client.get("/api/v1/positions/1")
        self.assertEqual(response.status_code, 404)

    def test_submit_application_success(self) -> None:
        office = _office()
        application = _application()
        session = SimpleNamespace(get=AsyncMock(side_effect=[office, office]))
        app = _build_app(_user(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.positions.position_management_service.submit_application",
            new=AsyncMock(return_value=application),
        ):
            response = client.post("/api/v1/positions/1/applications", json={"motivation": "Хочу"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "submitted")

    def test_submit_application_rejects_duplicate(self) -> None:
        office = _office()
        session = SimpleNamespace(get=AsyncMock(side_effect=[office, office]))
        app = _build_app(_user(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.positions.position_management_service.submit_application",
            new=AsyncMock(side_effect=PositionError("duplicate_application")),
        ):
            response = client.post("/api/v1/positions/1/applications", json={"motivation": "x"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "duplicate_application")

    def test_read_my_applications(self) -> None:
        application = _application()
        office = _office()
        session = SimpleNamespace(get=AsyncMock(return_value=office))
        app = _build_app(_user(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.positions.position_management_service.list_my_applications",
            new=AsyncMock(return_value=[application]),
        ):
            response = client.get("/api/v1/me/position-applications")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_withdraw_application_forbidden_for_other_user(self) -> None:
        application = _application(user_id=999)
        office = _office()
        session = SimpleNamespace(get=AsyncMock(side_effect=[application, office]))
        app = _build_app(_user(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.positions.position_management_service.withdraw_application",
            new=AsyncMock(side_effect=PermissionError("not_owner")),
        ):
            response = client.post("/api/v1/me/position-applications/10/withdraw")
        self.assertEqual(response.status_code, 403)

    def test_team_directory(self) -> None:
        office = _office()
        session = SimpleNamespace()
        app = _build_app(_user(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.positions.position_management_service.list_public_offices",
                new=AsyncMock(return_value=[office]),
            ),
            patch(
                "app.api.v1.positions.office_management_service.list_assignments",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get("/api/v1/team")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()[0]["is_vacant"])


if __name__ == "__main__":
    unittest.main()
