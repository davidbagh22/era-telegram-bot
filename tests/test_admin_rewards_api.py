from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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


def _reward(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, name="Приз", description="d", point_cost=50, quantity=3, is_active=True)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _redemption(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, reward_id=1, user_id=2, points_spent=50, status="pending", admin_comment=None)
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


class AdminRewardsApiTests(unittest.TestCase):
    def test_participant_forbidden(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/rewards")
        self.assertEqual(response.status_code, 403)

    def test_list_rewards(self) -> None:
        reward = _reward()
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.redemption_service.list_rewards_admin", new=AsyncMock(return_value=[reward])
        ):
            response = client.get("/api/v1/admin/rewards")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["name"], "Приз")

    def test_create_reward_requires_name_and_description(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/rewards", json={"name": " ", "description": "d", "point_cost": 10}
        )
        self.assertEqual(response.status_code, 422)

    def test_create_reward_rejects_non_positive_cost(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post(
            "/api/v1/admin/rewards", json={"name": "A", "description": "d", "point_cost": 0}
        )
        self.assertEqual(response.status_code, 422)

    def test_create_reward_success(self) -> None:
        reward = _reward()
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.redemption_service.create_reward", new=AsyncMock(return_value=reward)
        ):
            response = client.post(
                "/api/v1/admin/rewards", json={"name": "A", "description": "d", "point_cost": 10}
            )
        self.assertEqual(response.status_code, 200)

    def test_disable_reward_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/rewards/999/disable")
        self.assertEqual(response.status_code, 404)

    def test_disable_reward_success(self) -> None:
        reward = _reward()
        session = SimpleNamespace(get=AsyncMock(return_value=reward))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch("app.api.v1.admin.redemption_service.disable_reward", new=MagicMock()):
            response = client.post("/api/v1/admin/rewards/1/disable")
        self.assertEqual(response.status_code, 200)

    def test_list_redemptions(self) -> None:
        redemption = _redemption()
        reward = _reward()
        respondent = SimpleNamespace(id=2, first_name="Анна", last_name="ЭРА")
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.redemption_service.list_open_redemptions",
            new=AsyncMock(return_value=[(redemption, reward, respondent)]),
        ):
            response = client.get("/api/v1/admin/redemptions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["user_name"], "Анна ЭРА")

    def test_answer_redemption_requires_open_status(self) -> None:
        redemption = _redemption(status="exchanged")
        session = SimpleNamespace(get=AsyncMock(return_value=redemption))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/redemptions/1/answer", json={"answer": "ok"})
        self.assertEqual(response.status_code, 409)

    def test_answer_redemption_requires_non_blank_answer(self) -> None:
        redemption = _redemption()
        session = SimpleNamespace(get=AsyncMock(return_value=redemption))
        app = _build_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/redemptions/1/answer", json={"answer": "   "})
        self.assertEqual(response.status_code, 422)

    def test_answer_redemption_records_answer_even_when_delivery_fails(self) -> None:
        # Fire-and-forget, like every other admin notification in this
        # router — a transient Telegram delivery failure shouldn't block
        # the admin from recording their reply (the Redemptions list
        # isn't chat-mediated the way the Bot's own flow was).
        redemption = _redemption()
        reward = _reward()
        target = SimpleNamespace(id=2, telegram_id=777, first_name="A", last_name=None)
        session = SimpleNamespace(get=AsyncMock(side_effect=[redemption, reward, target]))
        app = _build_app(_admin(), session, bot=SimpleNamespace())
        client = TestClient(app)
        with (
            patch("app.api.v1.admin.safe_send", new=AsyncMock(return_value=False)),
            patch("app.api.v1.admin.redemption_service.answer_redemption", new=AsyncMock()) as answer_mock,
        ):
            response = client.post("/api/v1/admin/redemptions/1/answer", json={"answer": "ok"})
        self.assertEqual(response.status_code, 200)
        answer_mock.assert_awaited_once()

    def test_answer_redemption_success(self) -> None:
        redemption = _redemption()
        reward = _reward()
        target = SimpleNamespace(id=2, telegram_id=777, first_name="A", last_name=None)
        session = SimpleNamespace(get=AsyncMock(side_effect=[redemption, reward, target]))
        app = _build_app(_admin(), session, bot=SimpleNamespace())
        client = TestClient(app)
        with (
            patch("app.api.v1.admin.safe_send", new=AsyncMock(return_value=True)),
            patch("app.api.v1.admin.redemption_service.answer_redemption", new=AsyncMock()),
        ):
            response = client.post("/api/v1/admin/redemptions/1/answer", json={"answer": "ok"})
        self.assertEqual(response.status_code, 200)

    def test_exchange_redemption_maps_failure_code(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        result = SimpleNamespace(code="answer_required", redemption=None, reward=None)
        with patch(
            "app.api.v1.admin.redemption_service.exchange_redemption", new=AsyncMock(return_value=result)
        ):
            response = client.post("/api/v1/admin/redemptions/1/exchange")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "answer_required")

    def test_exchange_redemption_success_notifies_participant(self) -> None:
        redemption = _redemption(status="exchanged")
        reward = _reward()
        target = SimpleNamespace(id=2, telegram_id=777, first_name="A", last_name=None)
        result = SimpleNamespace(code="exchanged", redemption=redemption, reward=reward)
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session, bot=SimpleNamespace())
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.redemption_service.exchange_redemption", new=AsyncMock(return_value=result)
            ),
            patch("app.api.v1.admin.total_points", new=AsyncMock(return_value=0)),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post("/api/v1/admin/redemptions/1/exchange")
        self.assertEqual(response.status_code, 200)
        safe_send_mock.assert_awaited_once()

    def test_reject_redemption_maps_failure_code(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_admin(), session)
        client = TestClient(app)
        result = SimpleNamespace(code="already_closed", redemption=None, reward=None)
        with patch(
            "app.api.v1.admin.redemption_service.reject_redemption", new=AsyncMock(return_value=result)
        ):
            response = client.post("/api/v1/admin/redemptions/1/reject")
        self.assertEqual(response.status_code, 409)

    def test_reject_redemption_success(self) -> None:
        redemption = _redemption(status="rejected")
        reward = _reward()
        target = SimpleNamespace(id=2, telegram_id=777, first_name="A", last_name=None)
        result = SimpleNamespace(code="rejected", redemption=redemption, reward=reward)
        session = SimpleNamespace(get=AsyncMock(return_value=target))
        app = _build_app(_admin(), session, bot=SimpleNamespace())
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.redemption_service.reject_redemption", new=AsyncMock(return_value=result)
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post("/api/v1/admin/redemptions/1/reject")
        self.assertEqual(response.status_code, 200)
        safe_send_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
