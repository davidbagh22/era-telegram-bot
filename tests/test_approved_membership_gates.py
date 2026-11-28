from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.utils.constants import ApplicationStatus, Role


class ApprovedMembershipGateTests(unittest.TestCase):
    def _client(self, **user_overrides) -> TestClient:
        app = FastAPI()
        app.include_router(api_router)
        defaults = dict(
            id=1,
            telegram_id=1001,
            first_name="Тест",
            role=Role.PARTICIPANT,
            application_status=ApplicationStatus.PENDING,
            is_blocked=False,
            is_archived=False,
            permission_grants=[],
            departments=[],
            directions=[],
        )
        defaults.update(user_overrides)
        viewer = SimpleNamespace(**defaults)
        session = SimpleNamespace(
            get=AsyncMock(side_effect=AssertionError("DB read must not run for unapproved user")),
            scalar=AsyncMock(side_effect=AssertionError("DB read must not run for unapproved user")),
        )

        async def _session_override():
            yield session

        app.dependency_overrides[get_current_user] = lambda: viewer
        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_bot] = lambda: None
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token",
            feature_auctions="ALL",
            feature_surveys="ALL",
            feature_rewards="ALL",
        )
        return TestClient(app)

    def test_unapproved_and_inactive_users_receive_403_on_member_mutations(self) -> None:
        endpoints = [
            ("POST", "/api/v1/auctions/1/bid", {"amount": 50}),
            ("POST", "/api/v1/surveys/1/submit", {"answers": ["Да"]}),
            ("POST", "/api/v1/rewards/1/redeem", None),
            ("POST", "/api/v1/opportunities/1/apply", None),
            ("POST", "/api/v1/projects", {"idea": "Идея"}),
            ("POST", "/api/v1/projects/1/submit", None),
            ("POST", "/api/v1/projects/1/workspace/applications", {"role_id": 1, "text": "Хочу"}),
        ]
        for state_name, overrides in (
            ("pending", {"application_status": ApplicationStatus.PENDING}),
            ("needs_info", {"application_status": ApplicationStatus.NEEDS_INFO}),
            ("rejected", {"application_status": ApplicationStatus.REJECTED}),
            ("blocked", {"application_status": ApplicationStatus.APPROVED, "is_blocked": True}),
            ("archived", {"application_status": ApplicationStatus.APPROVED, "is_archived": True}),
        ):
            client = self._client(**overrides)
            for method, path, payload in endpoints:
                with self.subTest(state=state_name, method=method, path=path):
                    response = client.request(method, path, json=payload)
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json()["detail"], "approved_membership_required")
