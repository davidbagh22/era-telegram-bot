from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session
from app.api.v1.router import api_router
from app.database.models import Task, User
from app.services import leader_service


def _user(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1,
        telegram_id=555,
        first_name="Лидер",
        last_name=None,
        role="leader",
        is_blocked=False,
        is_archived=False,
        departments=[],
        directions=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _fake_session(get_results: dict) -> SimpleNamespace:
    async def _get(model, obj_id):
        return get_results.get((model, obj_id))

    return SimpleNamespace(get=AsyncMock(side_effect=_get))


def _build_app(user, session) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_bot] = lambda: None
    return app


class LeaderAccessTests(unittest.TestCase):
    def test_participant_is_denied(self) -> None:
        app = _build_app(_user(role="participant"), _fake_session({}))
        client = TestClient(app)
        response = client.get("/api/v1/leader/overview")
        self.assertEqual(response.status_code, 403)

    def test_leader_can_read_overview(self) -> None:
        app = _build_app(_user(), _fake_session({}))
        client = TestClient(app)
        with (
            patch("app.api.v1.leader.leader_service.list_scope_participants", new=AsyncMock(return_value=[])),
            patch("app.api.v1.leader.leader_service.list_scope_events", new=AsyncMock(return_value=[])),
            patch("app.api.v1.leader.leader_service.list_scope_projects", new=AsyncMock(return_value=[])),
            patch("app.api.v1.leader.leader_service.list_created_tasks", new=AsyncMock(return_value=[])),
        ):
            response = client.get("/api/v1/leader/overview")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["participants"], [])
        self.assertEqual(body["departments"], [])


class LeaderOpenTaskApiTests(unittest.TestCase):
    def test_create_open_task_returns_task_shape(self) -> None:
        app = _build_app(_user(), _fake_session({}))
        client = TestClient(app)
        created = Task(
            id=5,
            title="Открытая задача",
            description="d",
            deadline=datetime.now(timezone.utc),
            points=15,
            task_type="challenge",
            status="published",
            max_participants=3,
            creator_id=1,
        )
        with patch(
            "app.api.v1.leader.leader_service.create_open_task", new=AsyncMock(return_value=created)
        ):
            response = client.post(
                "/api/v1/leader/open-tasks",
                json={
                    "title": "Открытая задача",
                    "description": "d",
                    "deadline": "2026-09-01T18:00:00+00:00",
                    "points": 15,
                    "max_participants": 3,
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], 5)
        self.assertEqual(body["applications"], [])

    def test_create_open_task_invalid_payload_returns_422(self) -> None:
        app = _build_app(_user(), _fake_session({}))
        client = TestClient(app)
        with patch(
            "app.api.v1.leader.leader_service.create_open_task",
            new=AsyncMock(side_effect=ValueError("invalid_max_participants")),
        ):
            response = client.post(
                "/api/v1/leader/open-tasks",
                json={
                    "title": "t",
                    "description": "d",
                    "deadline": "2026-09-01T18:00:00+00:00",
                    "points": 15,
                    "max_participants": 0,
                },
            )
        self.assertEqual(response.status_code, 422)

    def test_read_open_tasks_returns_applications(self) -> None:
        app = _build_app(_user(), _fake_session({}))
        client = TestClient(app)
        task = Task(
            id=5,
            title="Открытая задача",
            description="d",
            deadline=datetime.now(timezone.utc),
            points=15,
            task_type="challenge",
            status="published",
            max_participants=3,
            creator_id=1,
        )
        applicant = SimpleNamespace(id=9, first_name="Иван", last_name=None, username="ivan")
        participant = SimpleNamespace(status="pending")
        result = leader_service.OpenTaskWithApplications(
            task=task,
            applications=[leader_service.OpenTaskApplication(participant=participant, applicant=applicant)],
        )
        with patch(
            "app.api.v1.leader.leader_service.list_open_tasks_with_applications",
            new=AsyncMock(return_value=[result]),
        ):
            response = client.get("/api/v1/leader/open-tasks")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["applications"][0]["user_id"], 9)


class LeaderDecideApplicationApiTests(unittest.TestCase):
    def test_decide_application_not_found_returns_404(self) -> None:
        app = _build_app(_user(), _fake_session({}))
        client = TestClient(app)
        response = client.post(
            "/api/v1/leader/open-tasks/5/applications/9/decide", json={"action": "accept"}
        )
        self.assertEqual(response.status_code, 404)

    def test_decide_application_capacity_reached_returns_409(self) -> None:
        task = Task(id=5, title="t", description="d", deadline=datetime.now(timezone.utc), points=1, creator_id=1)
        target = User(id=9, telegram_id=999, first_name="Иван")
        session = _fake_session({(Task, 5): task, (User, 9): target})
        app = _build_app(_user(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.leader.leader_service.decide_task_application",
            new=AsyncMock(side_effect=ValueError("capacity_reached")),
        ):
            response = client.post(
                "/api/v1/leader/open-tasks/5/applications/9/decide", json={"action": "accept"}
            )
        self.assertEqual(response.status_code, 409)

    def test_decide_application_not_owner_returns_403(self) -> None:
        task = Task(id=5, title="t", description="d", deadline=datetime.now(timezone.utc), points=1, creator_id=1)
        target = User(id=9, telegram_id=999, first_name="Иван")
        session = _fake_session({(Task, 5): task, (User, 9): target})
        app = _build_app(_user(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.leader.leader_service.decide_task_application",
            new=AsyncMock(side_effect=PermissionError("not_task_owner")),
        ):
            response = client.post(
                "/api/v1/leader/open-tasks/5/applications/9/decide", json={"action": "accept"}
            )
        self.assertEqual(response.status_code, 403)

    def test_decide_application_success_returns_updated_task(self) -> None:
        task = Task(
            id=5,
            title="t",
            description="d",
            deadline=datetime.now(timezone.utc),
            points=1,
            creator_id=1,
            task_type="challenge",
            max_participants=3,
        )
        target = User(id=9, telegram_id=999, first_name="Иван")
        session = _fake_session({(Task, 5): task, (User, 9): target})
        app = _build_app(_user(), session)
        client = TestClient(app)
        participant = SimpleNamespace(status="accepted")
        updated = leader_service.OpenTaskWithApplications(
            task=task,
            applications=[leader_service.OpenTaskApplication(participant=participant, applicant=target)],
        )
        with (
            patch("app.api.v1.leader.leader_service.decide_task_application", new=AsyncMock(return_value=participant)),
            patch(
                "app.api.v1.leader.leader_service.list_open_tasks_with_applications",
                new=AsyncMock(return_value=[updated]),
            ),
        ):
            response = client.post(
                "/api/v1/leader/open-tasks/5/applications/9/decide", json={"action": "accept"}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["applications"][0]["status"], "accepted")


if __name__ == "__main__":
    unittest.main()
