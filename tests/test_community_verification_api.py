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


if __name__ == "__main__":
    unittest.main()
