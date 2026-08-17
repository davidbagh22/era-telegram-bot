from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings


def _user(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=2,
        telegram_id=777,
        role="participant",
        is_blocked=False,
        is_archived=False,
        participation_status="active_member",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, telegram_id=555, role="admin", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _summary():
    from app.services.position_management_service import CandidateSummary

    return CandidateSummary(
        completed_projects=2,
        tasks_completed_on_time=8,
        tasks_completed_total=10,
        on_time_rate=80.0,
        events_attended=5,
        past_offices=1,
    )


def _build_app(user, session: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_current_user] = lambda: user

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    app.dependency_overrides[get_bot] = lambda: None
    return app


class MyPathApiTests(unittest.TestCase):
    def test_read_my_path(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_user(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.positions.position_management_service.candidate_summary",
                new=AsyncMock(return_value=_summary()),
            ),
            patch(
                "app.api.v1.positions.position_management_service.office_history",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.api.v1.positions.position_management_service.list_open_positions",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get("/api/v1/me/path")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["participation_status"], "active_member")
        self.assertEqual(response.json()["summary"]["completed_projects"], 2)


class CadreReserveApiTests(unittest.TestCase):
    def test_list_cadre_reserve(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        entry = SimpleNamespace(
            user_id=2, first_name="A", last_name=None, summary=_summary(), suggested_roles=["Куратор"]
        )
        with patch(
            "app.api.v1.admin.position_management_service.list_cadre_reserve",
            new=AsyncMock(return_value=[entry]),
        ):
            response = client.get("/api/v1/admin/cadre-reserve")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["suggested_roles"], ["Куратор"])

    def test_cadre_reserve_forbidden_for_participant(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_user(role="participant", permission_grants=[]), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/cadre-reserve")
        self.assertEqual(response.status_code, 403)

    def test_suggest_position_sends_notification(self) -> None:
        target = SimpleNamespace(id=2, telegram_id=777, first_name="A", last_name=None)
        office = SimpleNamespace(id=5, title="Куратор Медиа")
        session = SimpleNamespace(get=AsyncMock(side_effect=[target, office]), add=lambda obj: None)
        app = _build_app(_admin(), session)
        app.dependency_overrides[get_bot] = lambda: object()
        client = TestClient(app)
        with patch("app.api.v1.admin.safe_send", new=AsyncMock(return_value=True)):
            response = client.post("/api/v1/admin/cadre-reserve/2/suggest/5")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["notified"])

    def test_suggest_position_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/cadre-reserve/999/suggest/999")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
