from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
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
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
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
        with (
            patch("app.api.v1.leader.leader_service.create_open_task", new=AsyncMock(return_value=created)),
            # create_open_task() itself dispatches deliveries internally --
            # the endpoint reads them back afterwards via a separate call,
            # which needs its own mock now that create_open_task is mocked.
            patch("app.api.v1.leader.leader_service.list_task_deliveries", new=AsyncMock(return_value=[])),
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
        self.assertEqual(body["deliveries"], [])

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

    def test_decide_application_accept_passes_a_task_deep_link_keyboard(self) -> None:
        """The acceptance notification's "Открыть" button should deep-link
        to this specific task — see app/utils/deep_links.py::miniapp_task_url()."""
        task = Task(
            id=5, title="t", description="d", deadline=datetime.now(timezone.utc), points=1, creator_id=1
        )
        target = User(id=9, telegram_id=999, first_name="Иван")
        session = _fake_session({(Task, 5): task, (User, 9): target})
        app = FastAPI()
        app.include_router(api_router)

        async def _session_override():
            yield session

        app.dependency_overrides[get_current_user] = lambda: _user()
        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_bot] = lambda: None
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token",
            miniapp_url="https://era.example/app",
            miniapp_auth_secret="test-secret",
        )
        client = TestClient(app)
        with (
            patch("app.api.v1.leader.leader_service.decide_task_application", new=AsyncMock()) as decide_mock,
            patch(
                "app.api.v1.leader.leader_service.list_open_tasks_with_applications",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.post(
                "/api/v1/leader/open-tasks/5/applications/9/decide", json={"action": "accept"}
            )
        self.assertEqual(response.status_code, 200)
        keyboard = decide_mock.await_args.kwargs["keyboard"]
        url = keyboard.inline_keyboard[0][0].web_app.url
        self.assertEqual(url, "https://era.example/app/#/tasks/5")

    def test_decide_application_reject_passes_no_keyboard(self) -> None:
        task = Task(
            id=5, title="t", description="d", deadline=datetime.now(timezone.utc), points=1, creator_id=1
        )
        target = User(id=9, telegram_id=999, first_name="Иван")
        session = _fake_session({(Task, 5): task, (User, 9): target})
        app = FastAPI()
        app.include_router(api_router)

        async def _session_override():
            yield session

        app.dependency_overrides[get_current_user] = lambda: _user()
        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_bot] = lambda: None
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token",
            miniapp_url="https://era.example/app",
            miniapp_auth_secret="test-secret",
        )
        client = TestClient(app)
        with (
            patch("app.api.v1.leader.leader_service.decide_task_application", new=AsyncMock()) as decide_mock,
            patch(
                "app.api.v1.leader.leader_service.list_open_tasks_with_applications",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = client.post(
                "/api/v1/leader/open-tasks/5/applications/9/decide", json={"action": "reject"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(decide_mock.await_args.kwargs["keyboard"])


class LeaderAssignedTaskApiTests(unittest.TestCase):
    def test_create_assigned_task_returns_task_shape(self) -> None:
        assignee = User(id=9, telegram_id=999, first_name="Иван")
        session = _fake_session({(User, 9): assignee})
        app = _build_app(_user(), session)
        client = TestClient(app)
        created = Task(
            id=5,
            title="Задача",
            description="d",
            deadline=datetime.now(timezone.utc),
            points=10,
            assignee_id=9,
            creator_id=1,
            status="new",
        )
        with patch(
            "app.api.v1.leader.leader_service.create_assigned_task", new=AsyncMock(return_value=created)
        ):
            response = client.post(
                "/api/v1/leader/tasks",
                json={
                    "assignee_id": 9,
                    "title": "Задача",
                    "description": "d",
                    "deadline": "2026-09-01T18:00:00+00:00",
                    "points": 10,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], 5)

    def test_create_assigned_task_assignee_not_found_returns_404(self) -> None:
        session = _fake_session({})
        app = _build_app(_user(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/leader/tasks",
            json={
                "assignee_id": 9,
                "title": "Задача",
                "description": "d",
                "deadline": "2026-09-01T18:00:00+00:00",
                "points": 10,
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_create_assigned_task_passes_the_effective_miniapp_url(self) -> None:
        """create_assigned_task() builds the deep-link keyboard itself
        (it needs the just-flushed task.id) — see leader_service.py's own
        comment on why the URL is threaded through, not a keyboard."""
        assignee = User(id=9, telegram_id=999, first_name="Иван")
        session = _fake_session({(User, 9): assignee})
        app = FastAPI()
        app.include_router(api_router)

        async def _session_override():
            yield session

        app.dependency_overrides[get_current_user] = lambda: _user()
        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_bot] = lambda: None
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token",
            miniapp_url="https://era.example/app",
            miniapp_auth_secret="test-secret",
        )
        client = TestClient(app)
        created = Task(
            id=5,
            title="Задача",
            description="d",
            deadline=datetime.now(timezone.utc),
            points=10,
            assignee_id=9,
            creator_id=1,
            status="new",
        )
        with patch(
            "app.api.v1.leader.leader_service.create_assigned_task", new=AsyncMock(return_value=created)
        ) as create_mock:
            response = client.post(
                "/api/v1/leader/tasks",
                json={
                    "assignee_id": 9,
                    "title": "Задача",
                    "description": "d",
                    "deadline": "2026-09-01T18:00:00+00:00",
                    "points": 10,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(create_mock.await_args.kwargs["miniapp_url"], "https://era.example/app")


class OpenTaskDeliveryRetryApiTests(unittest.IsolatedAsyncioTestCase):
    """Real DB round trip through the actual endpoint (not mocked
    services) -- this one specifically needs the ownership check
    (task.creator_id != leader.id -> 404, not a delivery for someone
    else's task) verified against real rows, not a mock that would let a
    wrong assertion pass silently."""

    async def asyncSetUp(self) -> None:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.database.base import Base

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def _build_real_app(self, user) -> FastAPI:
        app = FastAPI()
        app.include_router(api_router)
        app.state.session_factory = self.session_factory
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token", general_chat_id=-100111
        )
        app.dependency_overrides[get_bot] = lambda: None  # bot_unavailable path
        return app

    async def test_retry_on_someone_elses_task_is_404(self) -> None:
        from app.database.models import TaskDelivery

        async with self.session_factory() as session:
            other_leader = User(telegram_id=2, first_name="Other", role="leader")
            session.add(other_leader)
            await session.flush()
            task = Task(
                title="t", description="d", creator_id=other_leader.id,
                deadline=datetime.now(timezone.utc), points=10, task_type="challenge",
                status="published", max_participants=3,
            )
            session.add(task)
            await session.flush()
            delivery = TaskDelivery(task_id=task.id, chat_key="general", chat_id=-100111, status="failed", error="x")
            session.add(delivery)
            await session.commit()
            task_id, delivery_id = task.id, delivery.id

        # A genuinely different leader -- id=999 can't collide with
        # other_leader's real autoincrement id from the DB above (id=1 did
        # once, silently turning this into a false-negative test).
        app = self._build_real_app(_user(id=999, telegram_id=555))
        client = TestClient(app)
        response = client.post(f"/api/v1/leader/open-tasks/{task_id}/deliveries/{delivery_id}/retry")
        self.assertEqual(response.status_code, 404)

    async def test_retry_own_task_delivery_without_bot_records_failure(self) -> None:
        async with self.session_factory() as session:
            leader = User(telegram_id=555, first_name="Лидер", role="leader")
            session.add(leader)
            await session.flush()
            leader_id = leader.id

        # id must match what was actually persisted above -- a plain
        # _user() default (id=1) would silently not match the real row.
        app = self._build_real_app(
            SimpleNamespace(
                id=leader_id, telegram_id=555, first_name="Лидер", role="leader",
                is_blocked=False, is_archived=False,
            )
        )
        client = TestClient(app)
        created = client.post(
            "/api/v1/leader/open-tasks",
            json={
                "title": "Задача",
                "description": "d",
                "deadline": "2026-09-01T18:00:00+00:00",
                "points": 10,
                "max_participants": 3,
                "destinations": ["general"],
            },
        )
        self.assertEqual(created.status_code, 200)
        body = created.json()
        self.assertEqual(len(body["deliveries"]), 1)
        # get_bot returns None in this app -> bot_unavailable, a real
        # failure recorded, not silently dropped.
        self.assertEqual(body["deliveries"][0]["status"], "failed")
        self.assertEqual(body["deliveries"][0]["error"], "bot_unavailable")

        retry = client.post(
            f"/api/v1/leader/open-tasks/{body['id']}/deliveries/{body['deliveries'][0]['id']}/retry"
        )
        self.assertEqual(retry.status_code, 200)
        retried_delivery = retry.json()["deliveries"][0]
        # Still failing (bot is still None) -- but it's a genuinely fresh
        # attempt, not just echoing the same stale row back.
        self.assertEqual(retried_delivery["status"], "failed")


if __name__ == "__main__":
    unittest.main()
