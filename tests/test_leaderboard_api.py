from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_session, get_settings
from app.api.security import create_session_token
from app.api.v1.router import api_router
from app.config import Settings
from app.services.leaderboard_service import LeaderboardEntry, LeaderboardSnapshot
from app.utils.constants import ParticipationStatus

SECRET = "test-secret"


def _settings() -> Settings:
    return Settings(bot_token="1234567890:test-token", miniapp_auth_secret=SECRET)


def _user() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        telegram_id=555,
        first_name="Dev",
        last_name=None,
        role="participant",
        application_status="approved",
        is_blocked=False,
        is_archived=False,
        participation_status=ParticipationStatus.NEW_MEMBER,
        permission_grants=[],
    )


def _snapshot() -> LeaderboardSnapshot:
    return LeaderboardSnapshot(
        entries=[
            LeaderboardEntry(
                rank=1, display_name="Top Person", points=100, growth_level="Лидер", is_you=False
            ),
            LeaderboardEntry(
                rank=2, display_name="Dev", points=40, growth_level="Участник", is_you=True
            ),
        ],
        me=LeaderboardEntry(
            rank=2, display_name="Dev", points=40, growth_level="Участник", is_you=True
        ),
    )


class LeaderboardApiTests(unittest.TestCase):
    def _build_app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(api_router)

        async def _session_override():
            yield SimpleNamespace()

        app.dependency_overrides[get_settings] = lambda: _settings()
        app.dependency_overrides[get_session] = _session_override
        return app

    def test_leaderboard_requires_auth(self) -> None:
        app = self._build_app()
        client = TestClient(app)
        response = client.get("/api/v1/leaderboard")
        self.assertEqual(response.status_code, 401)

    def test_leaderboard_returns_snapshot_for_authenticated_user(self) -> None:
        app = self._build_app()
        token, _ = create_session_token(telegram_id=555, secret=SECRET, ttl_seconds=3600)
        client = TestClient(app)
        with (
            patch("app.api.deps.get_user_by_telegram_id", new=AsyncMock(return_value=_user())),
            patch(
                "app.api.v1.leaderboard.build_leaderboard",
                new=AsyncMock(return_value=_snapshot()),
            ),
        ):
            response = client.get(
                "/api/v1/leaderboard", headers={"Authorization": f"Bearer {token}"}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["entries"]), 2)
        self.assertEqual(body["entries"][0]["display_name"], "Top Person")
        self.assertTrue(body["entries"][1]["is_you"])
        self.assertEqual(body["me"]["rank"], 2)

    def test_leaderboard_rejects_out_of_range_limit(self) -> None:
        app = self._build_app()
        token, _ = create_session_token(telegram_id=555, secret=SECRET, ttl_seconds=3600)
        client = TestClient(app)
        with patch("app.api.deps.get_user_by_telegram_id", new=AsyncMock(return_value=_user())):
            response = client.get(
                "/api/v1/leaderboard?limit=500",
                headers={"Authorization": f"Bearer {token}"},
            )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
