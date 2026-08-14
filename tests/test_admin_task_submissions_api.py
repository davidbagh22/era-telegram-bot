from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.models import Task, TaskSubmission, User


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, telegram_id=555, role="admin", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _participant() -> SimpleNamespace:
    return SimpleNamespace(
        id=2, telegram_id=777, role="participant", is_blocked=False, is_archived=False, permission_grants=[]
    )


def _build_app(user, session, bot=None) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    app.dependency_overrides[get_bot] = lambda: bot
    return app


def _fake_session(get_results: dict) -> SimpleNamespace:
    async def _get(model, obj_id):
        return get_results.get((model, obj_id))

    return SimpleNamespace(get=AsyncMock(side_effect=_get))


class AdminTaskSubmissionsApiTests(unittest.TestCase):
    def test_list_requires_manage_permission(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/task-submissions")
        self.assertEqual(response.status_code, 403)

    def test_list_pending_submissions(self) -> None:
        task = Task(id=9, title="Пост", description="d", points=15, creator_id=1)
        participant = User(id=2, telegram_id=777, first_name="Иван", last_name=None)
        submission = TaskSubmission(id=3, task_id=9, user_id=2, text="Готово", status="pending")
        session = _fake_session({(Task, 9): task, (User, 2): participant})
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.task_review_service.list_pending_submissions",
            new=AsyncMock(return_value=[submission]),
        ):
            response = client.get("/api/v1/admin/task-submissions")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body[0]["task_title"], "Пост")
        self.assertEqual(body[0]["participant_name"], "Иван")

    def test_decide_not_found(self) -> None:
        session = _fake_session({})
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/task-submissions/3/decide", json={"action": "approve", "comment": ""}
        )
        self.assertEqual(response.status_code, 404)

    def test_decide_invalid_action(self) -> None:
        task = Task(id=9, title="Пост", description="d", points=15, creator_id=1)
        participant = User(id=2, telegram_id=777, first_name="Иван", last_name=None)
        submission = TaskSubmission(id=3, task_id=9, user_id=2, text="Готово", status="pending")
        session = _fake_session({(TaskSubmission, 3): submission, (Task, 9): task, (User, 2): participant})
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/task-submissions/3/decide", json={"action": "nope", "comment": ""}
        )
        self.assertEqual(response.status_code, 422)

    def test_decide_approve_notifies_participant(self) -> None:
        task = Task(id=9, title="Пост", description="d", points=15, creator_id=1)
        participant = User(id=2, telegram_id=777, first_name="Иван", last_name=None)
        submission = TaskSubmission(id=3, task_id=9, user_id=2, text="Готово", status="pending")
        session = _fake_session({(TaskSubmission, 3): submission, (Task, 9): task, (User, 2): participant})
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        result = SimpleNamespace(
            submission=submission,
            admin_notice="Результат одобрен.",
            participant_notice="Ваш результат одобрен",
            points_awarded=15,
        )
        with (
            patch(
                "app.api.v1.admin.task_review_service.decide_submission",
                new=AsyncMock(return_value=result),
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post(
                "/api/v1/admin/task-submissions/3/decide", json={"action": "approve", "comment": ""}
            )
        self.assertEqual(response.status_code, 200)
        safe_send_mock.assert_awaited_once()

    def test_decide_approve_notification_links_to_the_task_in_mini_app(self) -> None:
        """The notification opens this exact task without relying on a URL fragment."""
        task = Task(id=9, title="Пост", description="d", points=15, creator_id=1)
        participant = User(id=2, telegram_id=777, first_name="Иван", last_name=None)
        submission = TaskSubmission(id=3, task_id=9, user_id=2, text="Готово", status="pending")
        session = _fake_session({(TaskSubmission, 3): submission, (Task, 9): task, (User, 2): participant})
        bot = SimpleNamespace()
        app = FastAPI()
        app.include_router(api_router)

        async def _session_override():
            yield session

        app.dependency_overrides[get_current_user] = lambda: _admin()
        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_bot] = lambda: bot
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token",
            miniapp_url="https://era.example/app",
            miniapp_auth_secret="test-secret",
        )
        client = TestClient(app)
        result = SimpleNamespace(
            submission=submission,
            admin_notice="Результат одобрен.",
            participant_notice="Ваш результат одобрен",
            points_awarded=15,
        )
        with (
            patch(
                "app.api.v1.admin.task_review_service.decide_submission",
                new=AsyncMock(return_value=result),
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post(
                "/api/v1/admin/task-submissions/3/decide", json={"action": "approve", "comment": ""}
            )
        self.assertEqual(response.status_code, 200)
        keyboard = safe_send_mock.await_args.args[3]
        url = keyboard.inline_keyboard[0][0].web_app.url
        parsed = urlsplit(url)
        self.assertEqual(parsed.fragment, "")
        self.assertEqual(parse_qs(parsed.query).get("eraPath"), ["tasks/9"])

    def test_decide_comment_required_maps_to_422(self) -> None:
        task = Task(id=9, title="Пост", description="d", points=15, creator_id=1)
        participant = User(id=2, telegram_id=777, first_name="Иван", last_name=None)
        submission = TaskSubmission(id=3, task_id=9, user_id=2, text="Готово", status="pending")
        session = _fake_session({(TaskSubmission, 3): submission, (Task, 9): task, (User, 2): participant})
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.task_review_service.decide_submission",
            new=AsyncMock(side_effect=ValueError("comment_required")),
        ):
            response = client.post(
                "/api/v1/admin/task-submissions/3/decide", json={"action": "reject", "comment": ""}
            )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
