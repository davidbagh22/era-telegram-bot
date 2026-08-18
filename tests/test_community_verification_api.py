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
    defaults = dict(id=1, telegram_id=555, role="admin", is_blocked=False, is_archived=False, permission_grants=[])
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _participant() -> SimpleNamespace:
    return SimpleNamespace(id=2, telegram_id=777, role="participant", is_blocked=False, is_archived=False, permission_grants=[])


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


class CommunityVerificationApiTests(unittest.TestCase):
    def test_status_forbidden_for_non_admin(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/community-verification/status")
        self.assertEqual(response.status_code, 403)

    def test_status_returns_campaign_and_segments(self) -> None:
        with (
            patch(
                "app.api.v1.community_verification.cv_service.complete_expired_campaigns",
                new=AsyncMock(return_value=0),
            ),
            patch(
                "app.api.v1.community_verification.cv_service.campaign_status",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        campaign=None,
                        segments=SimpleNamespace(
                            chat_members_total=10,
                            known_to_system=3,
                            pending=1,
                            approved=1,
                            rejected=1,
                            needs_info=0,
                            notified=0,
                            unreachable=0,
                            not_registered_estimate=7,
                        ),
                    )
                ),
            ),
        ):
            session = SimpleNamespace()
            app = _build_app(_admin(), session, bot=AsyncMock())
            client = TestClient(app)
            response = client.get("/api/v1/admin/community-verification/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["campaign"])
        self.assertEqual(body["segments"]["not_registered_estimate"], 7)

    def test_start_campaign_conflict_when_already_active(self) -> None:
        from app.services import community_verification_service as cv_service

        with patch(
            "app.api.v1.community_verification.cv_service.start_campaign",
            new=AsyncMock(side_effect=cv_service.CampaignError("campaign_already_active")),
        ):
            session = SimpleNamespace()
            app = _build_app(_admin(), session)
            client = TestClient(app)
            response = client.post(
                "/api/v1/admin/community-verification/start", json={"window_hours": 72}
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "campaign_already_active")

    def test_complete_campaign_requires_active_campaign(self) -> None:
        with patch(
            "app.api.v1.community_verification.cv_service.active_campaign",
            new=AsyncMock(return_value=None),
        ):
            session = SimpleNamespace()
            app = _build_app(_admin(), session)
            client = TestClient(app)
            response = client.post("/api/v1/admin/community-verification/complete")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "no_active_campaign")

    def test_send_launch_requires_active_campaign(self) -> None:
        with patch(
            "app.api.v1.community_verification.cv_service.active_campaign",
            new=AsyncMock(return_value=None),
        ):
            session = SimpleNamespace()
            app = _build_app(_admin(), session, bot=AsyncMock())
            client = TestClient(app)
            response = client.post("/api/v1/admin/community-verification/send-launch")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "no_active_campaign")

    def test_send_launch_returns_wave_summary(self) -> None:
        from app.services import community_verification_service as cv_service

        with (
            patch(
                "app.api.v1.community_verification.cv_service.active_campaign",
                new=AsyncMock(return_value=SimpleNamespace(id=1)),
            ),
            patch(
                "app.api.v1.community_verification.cv_service.post_launch_pin",
                new=AsyncMock(return_value="posted"),
            ),
            patch(
                "app.api.v1.community_verification.cv_service.send_launch_wave",
                new=AsyncMock(
                    return_value=cv_service.WaveResult(
                        total_recipients=5, already_attempted=0, sent=4, blocked=1, unreachable=0, failed=0
                    )
                ),
            ),
        ):
            session = SimpleNamespace()
            app = _build_app(_admin(), session, bot=AsyncMock())
            client = TestClient(app)
            response = client.post("/api/v1/admin/community-verification/send-launch")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pin_status"], "posted")
        self.assertEqual(body["sent"], 4)
        self.assertEqual(body["blocked"], 1)

    def test_not_registered_empty_without_any_campaign(self) -> None:
        with patch(
            "app.api.v1.community_verification.cv_service.latest_campaign",
            new=AsyncMock(return_value=None),
        ):
            session = SimpleNamespace()
            app = _build_app(_admin(), session)
            client = TestClient(app)
            response = client.get("/api/v1/admin/community-verification/not-registered")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_remind_selected_requires_nonempty_list(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session, bot=AsyncMock())
        client = TestClient(app)
        response = client.post("/api/v1/admin/community-verification/remind", json={"telegram_ids": []})
        self.assertEqual(response.status_code, 422)

    def test_remind_selected_requires_a_campaign(self) -> None:
        with patch(
            "app.api.v1.community_verification.cv_service.latest_campaign",
            new=AsyncMock(return_value=None),
        ):
            session = SimpleNamespace()
            app = _build_app(_admin(), session, bot=AsyncMock())
            client = TestClient(app)
            response = client.post(
                "/api/v1/admin/community-verification/remind", json={"telegram_ids": [1, 2]}
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "no_campaign")

    def test_remind_selected_returns_summary(self) -> None:
        from app.services import community_verification_service as cv_service

        with (
            patch(
                "app.api.v1.community_verification.cv_service.latest_campaign",
                new=AsyncMock(return_value=SimpleNamespace(id=1)),
            ),
            patch(
                "app.api.v1.community_verification.cv_service.remind_selected",
                new=AsyncMock(
                    return_value=cv_service.RemindSelectedResult(
                        requested=2, eligible=1, sent=1, blocked=0, unreachable=0, failed=0
                    )
                ),
            ),
        ):
            session = SimpleNamespace()
            app = _build_app(_admin(), session, bot=AsyncMock())
            client = TestClient(app)
            response = client.post(
                "/api/v1/admin/community-verification/remind", json={"telegram_ids": [1, 2]}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["requested"], 2)
        self.assertEqual(body["sent"], 1)

    def test_remove_selected_requires_nonempty_list(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session, bot=AsyncMock())
        client = TestClient(app)
        response = client.post("/api/v1/admin/community-verification/remove", json={"telegram_ids": []})
        self.assertEqual(response.status_code, 422)

    def test_remove_selected_returns_summary(self) -> None:
        from app.services import community_verification_service as cv_service

        with patch(
            "app.api.v1.community_verification.cv_service.remove_selected",
            new=AsyncMock(return_value=cv_service.RemoveSelectedResult(requested=2, removed=2, failed=0)),
        ):
            session = SimpleNamespace()
            app = _build_app(_admin(), session, bot=AsyncMock())
            client = TestClient(app)
            response = client.post(
                "/api/v1/admin/community-verification/remove", json={"telegram_ids": [1, 2]}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["removed"], 2)

    def test_remind_and_remove_forbidden_for_non_admin(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session, bot=AsyncMock())
        client = TestClient(app)
        remind = client.post("/api/v1/admin/community-verification/remind", json={"telegram_ids": [1]})
        remove = client.post("/api/v1/admin/community-verification/remove", json={"telegram_ids": [1]})
        self.assertEqual(remind.status_code, 403)
        self.assertEqual(remove.status_code, 403)


if __name__ == "__main__":
    unittest.main()
