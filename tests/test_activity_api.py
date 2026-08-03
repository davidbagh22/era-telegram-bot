from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings


def _user(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, telegram_id=555, role="participant")
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _event(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=10,
        title="Meetup",
        description="d",
        event_date=date.today() + timedelta(days=2),
        event_time=time(18, 0),
        location="HQ",
        format="offline",
        points_for_visit=5,
        project_id=None,
        participant_limit=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _task(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=20,
        title="Task",
        description="d",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        points=10,
        status="published",
        task_type="challenge",
        assignee_id=None,
        max_participants=None,
        audience_filter_json={},
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(session: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(
        bot_token="1234567890:test-token", bot_username="era_bot"
    )
    return app


class EventsApiTests(unittest.TestCase):
    def test_list_events_returns_scoped_rows(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.events.list_events",
                new=AsyncMock(return_value=[(_event(), None)]),
            ),
            patch("app.api.v1.events.available_places", new=AsyncMock(return_value="5")),
        ):
            response = client.get("/api/v1/events", params={"scope": "all"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["title"], "Meetup")
        self.assertIsNone(body[0]["registration_status"])

    def test_read_event_404_when_missing(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(session)
        client = TestClient(app)
        response = client.get("/api/v1/events/999")
        self.assertEqual(response.status_code, 404)

    def test_register_event_success(self) -> None:
        event = _event()
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(session)
        client = TestClient(app)
        registration = SimpleNamespace(status="registered")
        with (
            patch(
                "app.api.v1.events.register_for_event",
                new=AsyncMock(return_value=(registration, None)),
            ),
            patch("app.api.v1.events.available_places", new=AsyncMock(return_value="4")),
        ):
            response = client.post("/api/v1/events/10/register")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["registration_status"], "registered")

    def test_register_event_conflict(self) -> None:
        event = _event()
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(session)
        client = TestClient(app)
        with patch(
            "app.api.v1.events.register_for_event", new=AsyncMock(return_value=(None, "full"))
        ):
            response = client.post("/api/v1/events/10/register")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "full")

    def test_cancel_registration_not_found(self) -> None:
        event = _event()
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(session)
        client = TestClient(app)
        with patch(
            "app.api.v1.events._get_registration", new=AsyncMock(return_value=None)
        ):
            response = client.post("/api/v1/events/10/cancel")
        self.assertEqual(response.status_code, 404)

    def test_cancel_registration_blocked_by_rules(self) -> None:
        event = _event()
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(session)
        client = TestClient(app)
        registration = SimpleNamespace(status="attended")
        with (
            patch(
                "app.api.v1.events._get_registration", new=AsyncMock(return_value=registration)
            ),
            patch("app.api.v1.events.mark_not_coming", return_value=False),
        ):
            response = client.post("/api/v1/events/10/cancel")
        self.assertEqual(response.status_code, 409)


class TasksApiTests(unittest.TestCase):
    def test_list_tasks_returns_scope(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        task = _task()
        with (
            patch("app.api.v1.tasks.list_tasks", new=AsyncMock(return_value=[task])),
            patch(
                "app.api.v1.tasks.task_service.joined_task_ids", new=AsyncMock(return_value=set())
            ),
            patch(
                "app.api.v1.tasks.task_service.can_submit", new=AsyncMock(return_value=False)
            ),
        ):
            response = client.get("/api/v1/tasks", params={"scope": "available"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["title"], "Task")
        self.assertFalse(body[0]["can_submit"])

    def test_read_task_404_when_not_visible(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=_task()))
        app = _build_app(session)
        client = TestClient(app)
        with patch(
            "app.api.v1.tasks.task_service.can_view", new=AsyncMock(return_value=False)
        ):
            response = client.get("/api/v1/tasks/20")
        self.assertEqual(response.status_code, 404)

    def test_claim_task_404_when_missing(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(session)
        client = TestClient(app)
        response = client.post("/api/v1/tasks/999/claim")
        self.assertEqual(response.status_code, 404)

    def test_claim_task_conflict(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=_task()))
        app = _build_app(session)
        client = TestClient(app)
        with patch(
            "app.api.v1.tasks.task_service.claim", new=AsyncMock(return_value=(None, "full"))
        ):
            response = client.post("/api/v1/tasks/20/claim")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "task_full")

    def test_claim_task_success(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=_task()))
        app = _build_app(session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.tasks.task_service.claim",
                new=AsyncMock(return_value=(SimpleNamespace(status="pending"), None)),
            ),
            patch(
                "app.api.v1.tasks.task_service.joined_task_ids", new=AsyncMock(return_value=set())
            ),
            patch(
                "app.api.v1.tasks.task_service.can_submit", new=AsyncMock(return_value=False)
            ),
        ):
            response = client.post("/api/v1/tasks/20/claim")
        self.assertEqual(response.status_code, 200)

    def test_submit_deep_link_present_when_can_submit(self) -> None:
        session = SimpleNamespace(
            get=AsyncMock(return_value=_task()), scalar=AsyncMock(return_value=None)
        )
        app = _build_app(session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.tasks.task_service.joined_task_ids", new=AsyncMock(return_value=set())
            ),
            patch("app.api.v1.tasks.task_service.can_submit", new=AsyncMock(return_value=True)),
        ):
            response = client.get("/api/v1/tasks/20")
        self.assertEqual(
            response.json()["submit_deep_link"], "https://t.me/era_bot?start=task_submit_20"
        )

    def test_submit_deep_link_absent_when_cannot_submit(self) -> None:
        session = SimpleNamespace(
            get=AsyncMock(return_value=_task()), scalar=AsyncMock(return_value=None)
        )
        app = _build_app(session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.tasks.task_service.joined_task_ids", new=AsyncMock(return_value=set())
            ),
            patch("app.api.v1.tasks.task_service.can_submit", new=AsyncMock(return_value=False)),
        ):
            response = client.get("/api/v1/tasks/20")
        self.assertIsNone(response.json()["submit_deep_link"])


class ActivityApiTests(unittest.TestCase):
    def test_calendar_endpoint(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        item = SimpleNamespace(kind="event", id=1, title="Meetup", date="2026-08-10", time="18:00")
        with patch(
            "app.api.v1.activity.calendar_items", new=AsyncMock(return_value=[item])
        ):
            response = client.get("/api/v1/activity/calendar")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["kind"], "event")

    def test_history_endpoint(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        entry = SimpleNamespace(kind="points", title="Bonus", date="2026-08-01", detail="+10 баллов")
        with patch(
            "app.api.v1.activity.history_entries", new=AsyncMock(return_value=[entry])
        ):
            response = client.get("/api/v1/activity/history")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["detail"], "+10 баллов")


if __name__ == "__main__":
    unittest.main()
