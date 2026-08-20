from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings


def _leader(**overrides) -> SimpleNamespace:
    defaults = dict(id=2, telegram_id=777, role="leader", is_blocked=False, is_archived=False)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _participant(**overrides) -> SimpleNamespace:
    defaults = dict(id=3, telegram_id=888, role="participant", is_blocked=False, is_archived=False)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _goal(**overrides) -> SimpleNamespace:
    import datetime as dt

    defaults = dict(
        id=1,
        owner_id=2,
        scope_type="global",
        scope_id=None,
        period_type="month",
        period_start=dt.date(2026, 8, 1),
        period_end=dt.date(2026, 8, 31),
        title="Цель",
        metric=None,
        target=None,
        progress=0.0,
        status="active",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _report(**overrides) -> SimpleNamespace:
    import datetime as dt

    defaults = dict(
        id=1,
        period_start=dt.date(2026, 8, 17),
        period_end=dt.date(2026, 8, 23),
        scope_type="global",
        scope_id=None,
        office_assignment_id=None,
        status="green",
        main_result=None,
        blocker_type=None,
        blocker_note=None,
        next_priorities=[],
        needs_help=False,
        submitted_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _pulse(**overrides) -> SimpleNamespace:
    defaults = dict(
        system_snapshot={},
        pace_score=None,
        clarity_score=None,
        load_score=None,
        attention_text=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _view(*, report=None, pulse=None) -> SimpleNamespace:
    return SimpleNamespace(report=report or _report(), pulse=pulse or _pulse())


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


class LeadershipApiTests(unittest.TestCase):
    def test_participant_forbidden(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/leadership/me")
        self.assertEqual(response.status_code, 403)

    def test_read_me(self) -> None:
        session = SimpleNamespace(scalar=AsyncMock(side_effect=[0, 0]))
        app = _build_app(_leader(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.leadership.active_office_assignments", new=AsyncMock(return_value=[])
            ),
            patch(
                "app.api.v1.leadership.leadership_goal_service.list_goals",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.api.v1.leadership.leadership_report_service.current_report",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.v1.leadership.leadership_report_service.list_attention_items",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.api.v1.leadership.leader_service.list_scope_participants",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.get("/api/v1/leadership/me")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["current_week_report_submitted"])

    def test_create_goal(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_leader(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.leadership.leadership_goal_service.create_goal",
            new=AsyncMock(return_value=_goal()),
        ):
            response = client.post(
                "/api/v1/leadership/goals",
                json={
                    "title": "300 участников",
                    "period_start": "2026-08-01",
                    "period_end": "2026-08-31",
                    "target": 300,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Цель")

    def test_create_goal_requires_title(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_leader(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/leadership/goals",
            json={"title": "  ", "period_start": "2026-08-01", "period_end": "2026-08-31"},
        )
        self.assertEqual(response.status_code, 422)

    def test_update_goal_progress_forbidden_for_other_owner(self) -> None:
        goal = _goal(owner_id=999)
        session = SimpleNamespace(get=AsyncMock(return_value=goal))
        app = _build_app(_leader(), session)
        client = TestClient(app)
        response = client.patch("/api/v1/leadership/goals/1", json={"progress": 5})
        self.assertEqual(response.status_code, 403)

    def test_update_goal_progress_success(self) -> None:
        goal = _goal(owner_id=2)
        session = SimpleNamespace(get=AsyncMock(return_value=goal))
        app = _build_app(_leader(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.leadership.leadership_goal_service.update_progress", new=AsyncMock()
        ):
            response = client.patch("/api/v1/leadership/goals/1", json={"progress": 50})
        self.assertEqual(response.status_code, 200)

    def test_submit_report(self) -> None:
        session = SimpleNamespace(commit=AsyncMock())
        app = _build_app(_leader(), session)
        client = TestClient(app)
        result = _view(report=_report(status="red", needs_help=True))
        with patch(
            "app.api.v1.leadership.leadership_weekly_service.submit_weekly_pulse",
            new=AsyncMock(return_value=result),
        ):
            response = client.post(
                "/api/v1/leadership/reports",
                json={"status": "red", "needs_help": True, "blocker_note": "Нет ресурсов"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "red")
        session.commit.assert_awaited_once()

    def test_read_current_report_ensures_weekly_view(self) -> None:
        session = SimpleNamespace(commit=AsyncMock())
        app = _build_app(_leader(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.leadership.leadership_weekly_service.ensure_weekly_report",
            new=AsyncMock(return_value=_view()),
        ):
            response = client.get("/api/v1/leadership/reports/current")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], 1)
        self.assertEqual(response.json()["status"], "green")
        session.commit.assert_awaited_once()

    def test_resolve_attention_item_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_leader(), session)
        client = TestClient(app)
        response = client.post("/api/v1/leadership/attention/999/resolve", json={})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
