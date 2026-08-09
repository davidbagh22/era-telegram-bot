from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session
from app.api.v1.router import api_router


def _participant(**overrides) -> SimpleNamespace:
    defaults = dict(id=2, telegram_id=777, role="participant", is_blocked=False, is_archived=False)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _reward(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, name="Приз", description="d", point_cost=50, quantity=3, is_active=True)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(user, session: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    return app


class ParticipantRewardsApiTests(unittest.TestCase):
    def test_list_rewards(self) -> None:
        reward = _reward()
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with (
            patch("app.api.v1.rewards.redemption_service.list_visible_rewards", new=AsyncMock(return_value=[reward])),
            patch("app.api.v1.rewards.redemption_service.get_user_redemption", new=AsyncMock(return_value=None)),
        ):
            response = client.get("/api/v1/rewards")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body[0]["name"], "Приз")
        self.assertIsNone(body[0]["my_status"])

    def test_redeem_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.post("/api/v1/rewards/999/redeem")
        self.assertEqual(response.status_code, 404)

    def test_redeem_maps_value_error_to_409(self) -> None:
        reward = _reward()
        session = SimpleNamespace(get=AsyncMock(return_value=reward))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.rewards.redemption_service.redeem_reward",
            new=AsyncMock(side_effect=ValueError("insufficient_points")),
        ):
            response = client.post("/api/v1/rewards/1/redeem")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "insufficient_points")

    def test_redeem_success(self) -> None:
        reward = _reward()
        session = SimpleNamespace(get=AsyncMock(return_value=reward))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with (
            patch("app.api.v1.rewards.redemption_service.redeem_reward", new=AsyncMock()),
            patch("app.api.v1.rewards.redemption_service.get_user_redemption", new=AsyncMock(return_value=None)),
        ):
            response = client.post("/api/v1/rewards/1/redeem")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
