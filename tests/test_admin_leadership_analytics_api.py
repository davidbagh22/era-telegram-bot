from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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


class AdminLeadershipAnalyticsApiTests(unittest.TestCase):
    def test_read_leadership_analytics(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        payload = SimpleNamespace(
            vacancies_open=1,
            applications_by_status={"submitted": 2},
            active_leaders=3,
            open_blockers=0,
            avg_blocker_resolution_hours=None,
            goals_active=1,
            goals_completed=0,
            goals_overdue=0,
            goal_completion_rate=None,
            reports_expected=3,
            reports_submitted=1,
            reporting_discipline_rate=33.3,
            leadership_health_score=33.3,
        )
        with patch(
            "app.api.v1.admin.build_leadership_analytics", new=AsyncMock(return_value=payload)
        ):
            response = client.get("/api/v1/admin/leadership/analytics")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["active_leaders"], 3)

    def test_read_leader_workload(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        payload = SimpleNamespace(assignments=1, open_tasks=2, overdue_tasks=1, open_blockers=0)
        with patch("app.api.v1.admin.build_leader_workload", new=AsyncMock(return_value=payload)):
            response = client.get("/api/v1/admin/leadership/leaders/2/workload")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["overdue_tasks"], 1)

    def test_read_leadership_attention(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        item = SimpleNamespace(
            id=1,
            type="leader_blocker",
            severity="high",
            scope_type="global",
            scope_id=None,
            owner_id=2,
            responsible_id=None,
            status="open",
            resolution=None,
        )
        with patch(
            "app.api.v1.admin.leadership_report_service.list_attention_items",
            new=AsyncMock(return_value=[item]),
        ):
            response = client.get("/api/v1/admin/leadership/attention")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_participant_forbidden(self) -> None:
        session = SimpleNamespace()
        participant = SimpleNamespace(
            id=9, telegram_id=999, role="participant", is_blocked=False, is_archived=False, permission_grants=[]
        )
        app = _build_app(participant, session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/leadership/analytics")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
