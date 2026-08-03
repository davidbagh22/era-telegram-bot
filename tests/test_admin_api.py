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


def _target_user(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=10,
        telegram_id=999,
        first_name="New",
        last_name=None,
        city="City",
        occupation="Student",
        motivation="m",
        application_status="pending",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _project(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=20,
        title="Idea",
        short_description="d",
        status="initial_review",
        author_id=2,
        submitted_at=None,
        admin_comment=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(user, session: SimpleNamespace, bot=None) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    app.dependency_overrides[get_bot] = lambda: bot
    return app


class DashboardAccessTests(unittest.TestCase):
    def test_admin_can_read_dashboard(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        metrics = SimpleNamespace(values={"users_total": 5}, attention_total=3)
        with patch(
            "app.api.v1.admin.dashboard_metrics", new=AsyncMock(return_value=metrics)
        ):
            response = client.get("/api/v1/admin/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["attention_total"], 3)

    def test_participant_forbidden_from_dashboard(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/dashboard")
        self.assertEqual(response.status_code, 403)


class ApplicationsApiTests(unittest.TestCase):
    def test_list_applications_requires_admin(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/applications")
        self.assertEqual(response.status_code, 403)

    def test_approve_notifies_via_bot(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        decision = SimpleNamespace(changed=True, code="approved")
        with (
            patch(
                "app.api.v1.admin.approve_application", new=AsyncMock(return_value=decision)
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
            patch(
                "app.api.v1.admin.sync_user_chat_access", new=AsyncMock()
            ) as sync_mock,
        ):
            response = client.post("/api/v1/admin/applications/10/approve")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(safe_send_mock.await_count, 2)
        sync_mock.assert_awaited_once()

    def test_approve_conflict_when_already_rejected(self) -> None:
        target = _target_user(application_status="rejected")
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        decision = SimpleNamespace(changed=False, code="already_rejected")
        with patch(
            "app.api.v1.admin.approve_application", new=AsyncMock(return_value=decision)
        ):
            response = client.post("/api/v1/admin/applications/10/approve")
        self.assertEqual(response.status_code, 409)

    def test_approve_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/applications/999/approve")
        self.assertEqual(response.status_code, 404)

    def test_reject_requires_comment(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/applications/10/reject", json={"comment": "  "})
        self.assertEqual(response.status_code, 422)

    def test_reject_success(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        decision = SimpleNamespace(changed=True, code="rejected")
        with (
            patch("app.api.v1.admin.reject_application", new=AsyncMock(return_value=decision)),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()),
        ):
            response = client.post(
                "/api/v1/admin/applications/10/reject", json={"comment": "no fit"}
            )
        self.assertEqual(response.status_code, 200)

    def test_request_info_success(self) -> None:
        target = _target_user()
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        decision = SimpleNamespace(changed=True, code="needs_info")
        with (
            patch(
                "app.api.v1.admin.request_more_info", new=AsyncMock(return_value=decision)
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()),
        ):
            response = client.post(
                "/api/v1/admin/applications/10/request-info", json={"comment": "add phone"}
            )
        self.assertEqual(response.status_code, 200)


class AdminProjectsApiTests(unittest.TestCase):
    def test_list_requires_reviewer_permission(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=False)
        ):
            response = client.get("/api/v1/admin/projects")
        self.assertEqual(response.status_code, 403)

    def test_list_projects_for_review(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)),
            patch(
                "app.api.v1.admin.project_workflow_service.list_projects_for_review",
                new=AsyncMock(return_value=[_project()]),
            ),
        ):
            response = client.get("/api/v1/admin/projects")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["title"], "Idea")

    def test_decide_project_notifies_author(self) -> None:
        project = _project()
        author = SimpleNamespace(telegram_id=777)
        session = SimpleNamespace(get=AsyncMock(side_effect=[project, author]))
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        result = SimpleNamespace(notice="Проект одобрен", project=project)
        with (
            patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)),
            patch(
                "app.api.v1.admin.project_workflow_service.decide_project",
                new=AsyncMock(return_value=result),
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post(
                "/api/v1/admin/projects/20/decide",
                json={"action": "venue_approve", "comment": "ok"},
            )
        self.assertEqual(response.status_code, 200)
        safe_send_mock.assert_awaited_once()

    def test_decide_project_invalid_action(self) -> None:
        project = _project()
        session = SimpleNamespace(get=AsyncMock(return_value=project))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)):
            response = client.post(
                "/api/v1/admin/projects/20/decide",
                json={"action": "not_real", "comment": "ok"},
            )
        self.assertEqual(response.status_code, 422)

    def test_decide_project_requires_comment(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)):
            response = client.post(
                "/api/v1/admin/projects/20/decide",
                json={"action": "reject", "comment": ""},
            )
        self.assertEqual(response.status_code, 422)

    def test_decide_project_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)):
            response = client.post(
                "/api/v1/admin/projects/999/decide",
                json={"action": "reject", "comment": "no"},
            )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
