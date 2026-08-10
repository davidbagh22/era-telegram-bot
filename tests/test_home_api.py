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
from app.services.home_service import ActivityStats, GrowthProgress, HomeSnapshot
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


def _snapshot() -> HomeSnapshot:
    return HomeSnapshot(
        growth=GrowthProgress(level="participant", label="Участник", level_index=0, level_count=3),
        points_balance=15,
        activity=ActivityStats(points=15, projects=2, completed_tasks=3, portfolio_items=4),
        next_step=None,
        nearest_event=None,
        active_task=None,
        active_project=None,
        opportunities=[],
    )


class HomeApiTests(unittest.TestCase):
    def _build_app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(api_router)
        async def _session_override():
            yield SimpleNamespace()

        app.dependency_overrides[get_settings] = lambda: _settings()
        app.dependency_overrides[get_session] = _session_override
        return app

    def test_home_requires_auth(self) -> None:
        app = self._build_app()
        client = TestClient(app)
        response = client.get("/api/v1/home")
        self.assertEqual(response.status_code, 401)

    def test_home_returns_snapshot_for_authenticated_user(self) -> None:
        app = self._build_app()
        token, _ = create_session_token(telegram_id=555, secret=SECRET, ttl_seconds=3600)
        client = TestClient(app)
        with (
            patch("app.api.deps.get_user_by_telegram_id", new=AsyncMock(return_value=_user())),
            patch(
                "app.api.v1.home.build_home_snapshot", new=AsyncMock(return_value=_snapshot())
            ),
        ):
            response = client.get(
                "/api/v1/home", headers={"Authorization": f"Bearer {token}"}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["growth"]["level"], "participant")
        self.assertEqual(body["points_balance"], 15)
        self.assertEqual(
            body["activity"],
            {"points": 15, "projects": 2, "completed_tasks": 3, "portfolio_items": 4},
        )
        self.assertIsNone(body["next_step"])


if __name__ == "__main__":
    unittest.main()
