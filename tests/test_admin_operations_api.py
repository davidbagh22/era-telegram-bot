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


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, telegram_id=555, role="admin", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _participant(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=2, telegram_id=777, role="participant", is_blocked=False, is_archived=False, permission_grants=[]
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
    app.dependency_overrides[get_settings] = lambda: Settings(
        bot_token="1234567890:test-token", general_chat_id=-100
    )
    app.dependency_overrides[get_bot] = lambda: bot
    return app


def _project(**overrides) -> SimpleNamespace:
    defaults = dict(id=20, title="Идея", author_id=2, form_data={})
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _author() -> SimpleNamespace:
    return SimpleNamespace(id=2, telegram_id=777, first_name="Автор", last_name=None)


class TeamPostApiTests(unittest.TestCase):
    def test_list_requires_project_reviewer(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=False)):
            response = client.get("/api/v1/admin/projects/team-posts")
        self.assertEqual(response.status_code, 403)

    def test_list_pending_team_posts(self) -> None:
        project = _project(form_data={"team_search_post": "text", "team_search_status": "pending"})
        session = SimpleNamespace(get=AsyncMock(return_value=_author()))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)),
            patch(
                "app.api.v1.admin.project_workflow_service.list_projects_with_pending_team_post",
                new=AsyncMock(return_value=[project]),
            ),
        ):
            response = client.get("/api/v1/admin/projects/team-posts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["text"], "text")

    def test_prepare_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)):
            response = client.post("/api/v1/admin/projects/999/team-post/prepare")
        self.assertEqual(response.status_code, 404)

    def test_prepare_conflict_when_no_post(self) -> None:
        project = _project()
        session = SimpleNamespace(get=AsyncMock(side_effect=[project, _author()]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)):
            response = client.post("/api/v1/admin/projects/20/team-post/prepare")
        self.assertEqual(response.status_code, 409)

    def test_prepare_success(self) -> None:
        project = _project(form_data={"team_search_post": "text", "team_search_status": "pending"})
        session = SimpleNamespace(get=AsyncMock(side_effect=[project, _author(), _author()]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)):
            response = client.post("/api/v1/admin/projects/20/team-post/prepare")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "prepared")

    def test_edit_requires_min_length(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)):
            response = client.post("/api/v1/admin/projects/20/team-post/edit", json={"text": "short"})
        self.assertEqual(response.status_code, 422)

    def test_reject_notifies_author(self) -> None:
        project = _project(form_data={"team_search_post": "text", "team_search_status": "pending"})
        author = _author()
        session = SimpleNamespace(get=AsyncMock(side_effect=[project, author, author]))
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        with (
            patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post("/api/v1/admin/projects/20/team-post/reject")
        self.assertEqual(response.status_code, 200)
        safe_send_mock.assert_awaited_once()

    def test_publish_requires_prepared(self) -> None:
        project = _project(form_data={"team_search_post": "text", "team_search_status": "pending"})
        session = SimpleNamespace(get=AsyncMock(return_value=project))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)):
            response = client.post("/api/v1/admin/projects/20/team-post/publish")
        self.assertEqual(response.status_code, 409)

    def test_publish_success_notifies_chat_and_author(self) -> None:
        project = _project(form_data={"team_search_post": "text", "team_search_status": "prepared"})
        author = _author()
        session = SimpleNamespace(get=AsyncMock(side_effect=[project, author, author]))
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        with (
            patch("app.api.v1.admin.can_review_projects", new=AsyncMock(return_value=True)),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post("/api/v1/admin/projects/20/team-post/publish")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "published")
        self.assertEqual(safe_send_mock.await_count, 2)


class EventOperationsApiTests(unittest.TestCase):
    def test_operational_requires_event_reviewer(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/events/operational")
        self.assertEqual(response.status_code, 403)

    def test_operational_list(self) -> None:
        event = SimpleNamespace(
            id=1, title="E", event_date=SimpleNamespace(isoformat=lambda: "2026-01-01"),
            event_time=SimpleNamespace(isoformat=lambda: "18:00:00"), location="Онлайн",
            status="registration_open", points_for_visit=5,
        )
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.event_registration_service.list_operational_events",
                new=AsyncMock(return_value=[event]),
            ),
            patch(
                "app.api.v1.admin.event_registration_service.registration_stats",
                new=AsyncMock(return_value={"registered": 3, "free": 7}),
            ),
        ):
            response = client.get("/api/v1/admin/events/operational")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["registered"], 3)

    def test_participants_event_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/events/999/participants")
        self.assertEqual(response.status_code, 404)

    def test_participants_list(self) -> None:
        event = SimpleNamespace(id=1)
        registration = SimpleNamespace(id=8, status="registered")
        participant = SimpleNamespace(id=4, first_name="Анна", last_name=None)
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.event_registration_service.list_participants",
            new=AsyncMock(return_value=[(registration, participant)]),
        ):
            response = client.get("/api/v1/admin/events/1/participants")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["participant_name"], "Анна")

    def test_set_attendance_registration_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/events/1/registrations/999/attendance", json={"attended": True}
        )
        self.assertEqual(response.status_code, 404)

    def test_set_attendance_wrong_event_is_not_found(self) -> None:
        registration = SimpleNamespace(id=8, event_id=2, user_id=4, status="registered")
        session = SimpleNamespace(get=AsyncMock(return_value=registration))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/events/1/registrations/8/attendance", json={"attended": True}
        )
        self.assertEqual(response.status_code, 404)

    def test_set_attendance_success(self) -> None:
        registration = SimpleNamespace(id=8, event_id=1, user_id=4, status="registered")
        participant = SimpleNamespace(id=4, first_name="Анна", last_name=None)
        session = SimpleNamespace(get=AsyncMock(side_effect=[registration, participant]))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/events/1/registrations/8/attendance", json={"attended": True}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(registration.status, "attended")

    def test_award_points_event_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/events/999/award-attendance-points")
        self.assertEqual(response.status_code, 404)

    def test_award_points_notifies_newly_awarded(self) -> None:
        event = SimpleNamespace(id=1, title="E", points_for_visit=5)
        awarded_user = SimpleNamespace(telegram_id=999)
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        bot = SimpleNamespace()
        app = _build_app(_admin(), session, bot=bot)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.event_registration_service.award_attendance_points",
                new=AsyncMock(return_value=[awarded_user]),
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post("/api/v1/admin/events/1/award-attendance-points")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["awarded_count"], 1)
        safe_send_mock.assert_awaited_once()

    def test_award_points_notification_links_to_the_event_in_mini_app(self) -> None:
        event = SimpleNamespace(id=1, title="E", points_for_visit=5)
        awarded_user = SimpleNamespace(telegram_id=999)
        session = SimpleNamespace(get=AsyncMock(return_value=event))
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
            general_chat_id=-100,
            miniapp_url="https://era.example/app",
            miniapp_auth_secret="test-secret",
        )
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.event_registration_service.award_attendance_points",
                new=AsyncMock(return_value=[awarded_user]),
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post("/api/v1/admin/events/1/award-attendance-points")
        self.assertEqual(response.status_code, 200)
        keyboard = safe_send_mock.await_args.args[3]
        url = keyboard.inline_keyboard[0][0].web_app.url
        parsed = urlsplit(url)
        self.assertEqual(parsed.fragment, "")
        self.assertEqual(parse_qs(parsed.query).get("eraPath"), ["events/1"])


class PartnerCatalogApiTests(unittest.TestCase):
    def test_participant_forbidden(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/partners")
        self.assertEqual(response.status_code, 403)

    def test_create_partner_requires_name_and_description(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/partners", json={"name": "  ", "description": "d"}
        )
        self.assertEqual(response.status_code, 422)

    def test_create_partner_success(self) -> None:
        partner = SimpleNamespace(id=1, name="Acme", description="d", source_url=None, is_active=True, is_archived=False)
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.opportunity_service.create_partner", new=AsyncMock(return_value=partner)
        ):
            response = client.post(
                "/api/v1/admin/partners", json={"name": "Acme", "description": "d"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Acme")

    def test_set_active_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/partners/999/active", json={"active": False})
        self.assertEqual(response.status_code, 404)

    def test_archive_partner_success(self) -> None:
        partner = SimpleNamespace(id=1, name="Acme", description="d", source_url=None, is_active=True, is_archived=False)
        session = SimpleNamespace(get=AsyncMock(return_value=partner))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/partners/1/archive")
        self.assertEqual(response.status_code, 200)


class OfferCatalogApiTests(unittest.TestCase):
    def test_create_offer_requires_valid_partner(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/offers",
            json={"partner_id": 1, "title": "T", "description": "d", "point_cost": 10},
        )
        self.assertEqual(response.status_code, 404)

    def test_create_offer_rejects_negative_point_cost(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/offers",
            json={"partner_id": 1, "title": "T", "description": "d", "point_cost": -1},
        )
        self.assertEqual(response.status_code, 422)

    def test_create_offer_success(self) -> None:
        partner = SimpleNamespace(id=1, name="Acme", is_archived=False)
        offer = SimpleNamespace(
            id=5, partner_id=1, title="T", description="d", point_cost=10, quantity=None,
            expires_at=None, instruction=None, source_url=None, is_active=True, is_archived=False,
        )
        session = SimpleNamespace(get=AsyncMock(return_value=partner))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.opportunity_service.create_offer", new=AsyncMock(return_value=offer)
        ):
            response = client.post(
                "/api/v1/admin/offers", json={"partner_id": 1, "title": "T", "description": "d", "point_cost": 10},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "T")

    def test_set_active_offer_not_found(self) -> None:
        app = _build_app(_admin(), SimpleNamespace())
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.opportunity_service.get_offer_with_partner", new=AsyncMock(return_value=None)
        ):
            response = client.post("/api/v1/admin/offers/999/active", json={"active": False})
        self.assertEqual(response.status_code, 404)

    def test_archive_offer_success(self) -> None:
        partner = SimpleNamespace(id=1, name="Acme")
        offer = SimpleNamespace(
            id=5, partner_id=1, title="T", description="d", point_cost=10, quantity=None,
            expires_at=None, instruction=None, source_url=None, is_active=True, is_archived=False,
        )
        app = _build_app(_admin(), SimpleNamespace())
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.opportunity_service.get_offer_with_partner",
            new=AsyncMock(return_value=(offer, partner)),
        ):
            response = client.post("/api/v1/admin/offers/5/archive")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_archived"])


if __name__ == "__main__":
    unittest.main()
