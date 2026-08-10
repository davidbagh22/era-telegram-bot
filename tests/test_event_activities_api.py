from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings


def _participant(**overrides) -> SimpleNamespace:
    defaults = dict(id=2, telegram_id=777, role="participant", is_blocked=False, is_archived=False)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _leader(**overrides) -> SimpleNamespace:
    defaults = dict(id=3, telegram_id=888, role="leader")
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, telegram_id=555, role="admin", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _event(**overrides) -> SimpleNamespace:
    defaults = dict(id=10, title="Событие", additional_info=None)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _activity(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, event_id=10, title="Активность", description="d", submission_type="text", points=20, is_active=True
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _submission_row(**overrides):
    defaults = dict(
        submission=SimpleNamespace(id=1, status="pending", text="ok", file_type=None),
        activity=_activity(),
        event=_event(),
        user=SimpleNamespace(id=2, first_name="Анна", last_name="ЭРА"),
    )
    defaults.update(overrides)
    return (defaults["submission"], defaults["activity"], defaults["event"], defaults["user"])


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


class ParticipantEventActivitiesApiTests(unittest.TestCase):
    def test_event_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/events/999/activities")
        self.assertEqual(response.status_code, 404)

    def test_not_registered_returns_409(self) -> None:
        event = _event()
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.events.event_activity_service.list_activities_for_participant",
            new=AsyncMock(return_value=None),
        ):
            response = client.get("/api/v1/events/10/activities")
        self.assertEqual(response.status_code, 409)

    def test_list_activities_success(self) -> None:
        event = _event()
        activity = _activity()
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(_participant(), session)
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token", bot_username="era_test_bot"
        )
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.events.event_activity_service.list_activities_for_participant",
                new=AsyncMock(return_value=[activity]),
            ),
            patch(
                "app.api.v1.events.event_activity_service.get_submission", new=AsyncMock(return_value=None)
            ),
        ):
            response = client.get("/api/v1/events/10/activities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body[0]["title"], "Активность")
        self.assertIsNotNone(body[0]["submit_deep_link"])


class LeaderEventActivitiesApiTests(unittest.TestCase):
    def test_participant_forbidden(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/leader/activities")
        self.assertEqual(response.status_code, 403)

    def test_list_pending(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_leader(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.leader.event_activity_service.list_leader_pending",
            new=AsyncMock(return_value=[_submission_row()]),
        ):
            response = client.get("/api/v1/leader/activities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["user_name"], "Анна ЭРА")

    def test_decide_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_leader(), session)
        client = TestClient(app)
        response = client.post("/api/v1/leader/activities/1/decide", json={"action": "approve"})
        self.assertEqual(response.status_code, 404)

    def test_decide_already_reviewed(self) -> None:
        submission = SimpleNamespace(id=1, status="approved", user_id=2, text="ok", file_type=None)
        session = SimpleNamespace(get=AsyncMock(return_value=submission))
        app = _build_app(_leader(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.leader.event_activity_service.leader_decide", new=AsyncMock(return_value=None)
        ):
            response = client.post("/api/v1/leader/activities/1/decide", json={"action": "approve"})
        self.assertEqual(response.status_code, 409)

    def test_decide_approve_notifies_participant_and_admins(self) -> None:
        submission = SimpleNamespace(id=1, status="leader_approved", user_id=2, text="ok", file_type=None)
        activity = _activity()
        target = SimpleNamespace(id=2, telegram_id=777, first_name="Анна", last_name=None)
        event = _event()
        session = SimpleNamespace(get=AsyncMock(side_effect=[submission, target, event]))
        app = _build_app(_leader(), session, bot=SimpleNamespace())
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.leader.event_activity_service.leader_decide",
                new=AsyncMock(return_value=activity),
            ),
            patch("app.api.v1.leader.safe_send", new=AsyncMock()) as safe_send_mock,
            patch("app.api.v1.leader.notify_admins", new=AsyncMock()) as notify_admins_mock,
        ):
            response = client.post("/api/v1/leader/activities/1/decide", json={"action": "approve"})
        self.assertEqual(response.status_code, 200)
        safe_send_mock.assert_awaited_once()
        notify_admins_mock.assert_awaited_once()


class AdminEventActivitiesApiTests(unittest.TestCase):
    def test_participant_forbidden(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/activities/submissions")
        self.assertEqual(response.status_code, 403)

    def test_list_activities_for_event(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.event_activity_service.list_activities_admin",
            new=AsyncMock(return_value=[_activity()]),
        ):
            response = client.get("/api/v1/admin/events/10/activities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["title"], "Активность")

    def test_create_activities_event_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/events/999/activities", json={"lines": "A | 10 | text | d"})
        self.assertEqual(response.status_code, 404)

    def test_create_activities_no_valid_lines(self) -> None:
        event = _event()
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.event_activity_service.create_activities_bulk",
            new=AsyncMock(return_value=(0, 3)),
        ):
            response = client.post("/api/v1/admin/events/10/activities", json={"lines": "garbage"})
        self.assertEqual(response.status_code, 422)

    def test_create_activities_success(self) -> None:
        event = _event()
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.event_activity_service.create_activities_bulk",
                new=AsyncMock(return_value=(1, 0)),
            ),
            patch(
                "app.api.v1.admin.event_activity_service.list_activities_admin",
                new=AsyncMock(return_value=[_activity()]),
            ),
        ):
            response = client.post(
                "/api/v1/admin/events/10/activities", json={"lines": "A | 10 | text | d"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)

    def test_send_already_sent(self) -> None:
        event = _event(additional_info="[ERA_ACTIVITIES_SENT]")
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.event_activity_service.activities_already_sent", return_value=True
        ):
            response = client.post("/api/v1/admin/events/10/activities/send")
        self.assertEqual(response.status_code, 409)

    def test_send_no_active_activities(self) -> None:
        event = _event()
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.event_activity_service.activities_already_sent", return_value=False
            ),
            patch(
                "app.api.v1.admin.event_activity_service.list_activities_admin",
                new=AsyncMock(return_value=[_activity(is_active=False)]),
            ),
        ):
            response = client.post("/api/v1/admin/events/10/activities/send")
        self.assertEqual(response.status_code, 422)

    def test_send_success(self) -> None:
        event = _event()
        recipient = SimpleNamespace(id=2, telegram_id=777)
        session = SimpleNamespace(get=AsyncMock(return_value=event))
        app = _build_app(_admin(), session, bot=SimpleNamespace())
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.event_activity_service.activities_already_sent", return_value=False
            ),
            patch(
                "app.api.v1.admin.event_activity_service.list_activities_admin",
                new=AsyncMock(return_value=[_activity()]),
            ),
            patch(
                "app.api.v1.admin.event_activity_service.send_recipients",
                new=AsyncMock(return_value=[recipient]),
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
            patch(
                "app.api.v1.admin.event_activity_service.mark_activities_sent", new=lambda e: None
            ),
        ):
            response = client.post("/api/v1/admin/events/10/activities/send")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sent"], 1)
        safe_send_mock.assert_awaited_once()

    def test_list_submissions(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.event_activity_service.list_reviewable_submissions",
            new=AsyncMock(return_value=[_submission_row()]),
        ):
            response = client.get("/api/v1/admin/activities/submissions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["user_name"], "Анна ЭРА")

    def test_decide_submission_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/activities/submissions/1/decide", json={"action": "approve"}
        )
        self.assertEqual(response.status_code, 404)

    def test_decide_submission_already_reviewed(self) -> None:
        submission = SimpleNamespace(id=1, status="approved", user_id=2, text="ok", file_type=None)
        session = SimpleNamespace(get=AsyncMock(return_value=submission))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.event_activity_service.admin_decide", new=AsyncMock(return_value=None)
        ):
            response = client.post(
                "/api/v1/admin/activities/submissions/1/decide", json={"action": "approve"}
            )
        self.assertEqual(response.status_code, 409)

    def test_decide_submission_approve_success(self) -> None:
        submission = SimpleNamespace(id=1, status="approved", user_id=2, text="ok", file_type=None)
        activity = _activity()
        target = SimpleNamespace(id=2, telegram_id=777, first_name="Анна", last_name=None)
        event = _event()
        session = SimpleNamespace(get=AsyncMock(side_effect=[submission, target, event]))
        app = _build_app(_admin(), session, bot=SimpleNamespace())
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.event_activity_service.admin_decide",
                new=AsyncMock(return_value=activity),
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post(
                "/api/v1/admin/activities/submissions/1/decide", json={"action": "approve"}
            )
        self.assertEqual(response.status_code, 200)
        safe_send_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
