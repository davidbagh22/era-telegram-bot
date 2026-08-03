from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.projects import _notify_reviewers
from app.api.v1.router import api_router
from app.config import Settings
from app.services.project_workspace_service import ProjectWorkspaceSnapshot


def _user(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, telegram_id=555, first_name="Dev", last_name=None, username=None)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _project(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=10,
        title="Idea",
        short_description="d",
        status="draft",
        author_id=1,
        updated_at=datetime.now(timezone.utc),
        submitted_at=None,
        admin_comment=None,
        form_data={},
        generated_document=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(session: SimpleNamespace, bot=None) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    app.dependency_overrides[get_bot] = lambda: bot
    return app


class ProjectsListApiTests(unittest.TestCase):
    def test_list_projects_default_scope(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        with patch(
            "app.api.v1.projects.project_workflow_service.list_projects_for_user",
            new=AsyncMock(return_value=[_project()]),
        ):
            response = client.get("/api/v1/projects")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["title"], "Idea")


class ProjectQuestionsApiTests(unittest.TestCase):
    def test_questions_route_is_not_shadowed_by_project_id_route(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        response = client.get("/api/v1/projects/questions")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreater(len(body), 0)
        keys = {item["key"] for item in body}
        self.assertIn("idea", keys)
        self.assertNotIn("proposed_date", keys)
        self.assertNotIn("proposed_time", keys)


class ProjectDetailApiTests(unittest.TestCase):
    def test_owner_can_view(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=_project(author_id=1)))
        app = _build_app(session)
        client = TestClient(app)
        response = client.get("/api/v1/projects/10")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["can_edit"])

    def test_stranger_cannot_view_draft(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=_project(author_id=999, status="draft")))
        app = _build_app(session)
        client = TestClient(app)
        response = client.get("/api/v1/projects/10")
        self.assertEqual(response.status_code, 404)

    def test_stranger_can_view_open_project(self) -> None:
        session = SimpleNamespace(
            get=AsyncMock(return_value=_project(author_id=999, status="approved"))
        )
        app = _build_app(session)
        client = TestClient(app)
        response = client.get("/api/v1/projects/10")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["can_edit"])

    def test_missing_project_404(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(session)
        client = TestClient(app)
        response = client.get("/api/v1/projects/999")
        self.assertEqual(response.status_code, 404)


class ProjectWorkspaceApiTests(unittest.TestCase):
    def test_workspace_route_returns_snapshot(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        project = _project(id=10, author_id=1, status="approved")
        snapshot = ProjectWorkspaceSnapshot(
            project=project,
            can_manage=True,
            viewer_membership_status=None,
            roles=[],
            members=[],
            milestones=[],
            tasks=[],
            events=[],
        )
        with (
            patch(
                "app.api.v1.projects.project_workspace_service.require_project",
                new=AsyncMock(return_value=project),
            ),
            patch(
                "app.api.v1.projects.project_workspace_service.workspace_snapshot",
                new=AsyncMock(return_value=snapshot),
            ),
        ):
            response = client.get("/api/v1/projects/10/workspace")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project"]["id"], 10)
        self.assertEqual(response.json()["progress_percent"], 0)


class ProjectCreateApiTests(unittest.TestCase):
    def test_create_returns_new_draft(self) -> None:
        session = SimpleNamespace(commit=AsyncMock())
        app = _build_app(session)
        client = TestClient(app)
        with patch(
            "app.api.v1.projects.project_workflow_service.create_draft",
            new=AsyncMock(return_value=_project(id=20, title="Новая идея")),
        ):
            response = client.post("/api/v1/projects", json={"idea": "Новая идея"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], 20)
        session.commit.assert_awaited_once()


class ProjectUpdateApiTests(unittest.TestCase):
    def test_update_rejected_when_not_editable(self) -> None:
        session = SimpleNamespace(
            get=AsyncMock(return_value=_project(author_id=1, status="initial_review"))
        )
        app = _build_app(session)
        client = TestClient(app)
        response = client.patch("/api/v1/projects/10", json={"answers": {"title": "x"}})
        self.assertEqual(response.status_code, 409)

    def test_update_forbidden_for_non_owner(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=_project(author_id=999)))
        app = _build_app(session)
        client = TestClient(app)
        response = client.patch("/api/v1/projects/10", json={"answers": {"title": "x"}})
        self.assertEqual(response.status_code, 404)

    def test_update_success(self) -> None:
        project = _project(author_id=1, status="draft")
        session = SimpleNamespace(get=AsyncMock(return_value=project))
        app = _build_app(session)
        client = TestClient(app)
        response = client.patch(
            "/api/v1/projects/10", json={"answers": {"title": "Новый заголовок"}}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(project.title, "Новый заголовок")


class ProjectSubmitApiTests(unittest.TestCase):
    def test_submit_notifies_via_bot_when_available(self) -> None:
        project = _project(author_id=1, status="draft")
        session = SimpleNamespace(get=AsyncMock(return_value=project))
        bot = SimpleNamespace()
        app = _build_app(session, bot=bot)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.projects.project_workflow_service.submit_for_review",
                new=AsyncMock(return_value="DOCUMENT TEXT"),
            ),
            patch(
                "app.api.v1.projects._notify_reviewers", new=AsyncMock()
            ) as notify_mock,
        ):
            response = client.post("/api/v1/projects/10/submit")
        self.assertEqual(response.status_code, 200)
        notify_mock.assert_awaited_once()

    def test_submit_skips_notification_when_no_bot(self) -> None:
        project = _project(author_id=1, status="draft")
        session = SimpleNamespace(get=AsyncMock(return_value=project))
        app = _build_app(session, bot=None)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.projects.project_workflow_service.submit_for_review",
                new=AsyncMock(return_value="DOCUMENT TEXT"),
            ),
            patch("app.api.v1.projects._notify_reviewers", new=AsyncMock()) as notify_mock,
        ):
            response = client.post("/api/v1/projects/10/submit")
        self.assertEqual(response.status_code, 200)
        notify_mock.assert_not_awaited()

    def test_submit_conflict_when_not_submittable(self) -> None:
        project = _project(author_id=1, status="initial_review")
        session = SimpleNamespace(get=AsyncMock(return_value=project))
        app = _build_app(session)
        client = TestClient(app)
        response = client.post("/api/v1/projects/10/submit")
        self.assertEqual(response.status_code, 409)


class ProjectCancelApiTests(unittest.TestCase):
    def test_cancel_success(self) -> None:
        project = _project(author_id=1, status="draft")
        session = SimpleNamespace(get=AsyncMock(return_value=project))
        app = _build_app(session)
        client = TestClient(app)
        with patch(
            "app.api.v1.projects.project_workflow_service.cancel_project", new=AsyncMock()
        ) as cancel_mock:
            response = client.post("/api/v1/projects/10/cancel")
        self.assertEqual(response.status_code, 200)
        cancel_mock.assert_awaited_once()

    def test_cancel_conflict_when_not_cancellable(self) -> None:
        project = _project(author_id=1, status="initial_review")
        session = SimpleNamespace(get=AsyncMock(return_value=project))
        app = _build_app(session)
        client = TestClient(app)
        response = client.post("/api/v1/projects/10/cancel")
        self.assertEqual(response.status_code, 409)


class FakeBot:
    def __init__(self) -> None:
        self.messages = []
        self.documents = []

    async def send_message(self, chat_id, text, reply_markup=None) -> None:
        self.messages.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )

    async def send_document(self, chat_id, document, caption=None, reply_markup=None) -> None:
        self.documents.append(
            {
                "chat_id": chat_id,
                "document": document,
                "caption": caption,
                "reply_markup": reply_markup,
            }
        )


class ProjectNotificationDeepLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_review_notification_links_to_exact_admin_project(self) -> None:
        bot = FakeBot()
        settings = Settings(
            bot_token="1234567890:test-token",
            admin_ids=[100],
            miniapp_auth_secret="secret",
            miniapp_url="https://era.example/app/",
        )

        await _notify_reviewers(
            bot,
            settings,
            _project(id=10, title="Media Lab"),
            _user(username="leader"),
            "DOCUMENT",
        )

        self.assertEqual(bot.messages[0]["chat_id"], 100)
        button = bot.messages[0]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.text, "Открыть модерацию")
        self.assertEqual(button.url, "https://era.example/app/#/admin/projects/10")


if __name__ == "__main__":
    unittest.main()
