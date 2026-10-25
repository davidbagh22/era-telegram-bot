from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session
from app.api.v1.router import api_router
from app.config import Settings


def _participant(**overrides) -> SimpleNamespace:
    defaults = dict(id=2, telegram_id=777, role="participant", is_blocked=False, is_archived=False)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _auction(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1,
        title="Лот",
        description="d",
        status="active",
        starts_at=datetime.now(timezone.utc) - timedelta(days=1),
        minimum_bid=100,
        bid_step=10,
        ends_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
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


class ParticipantAuctionsApiTests(unittest.TestCase):
    def test_list_auctions(self) -> None:
        auction = _auction()
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.auctions.auction_service.list_active_auctions",
                new=AsyncMock(return_value=[auction]),
            ),
            patch(
                "app.api.v1.auctions.auction_service.top_bid_with_user",
                new=AsyncMock(return_value=(None, None)),
            ),
            patch(
                "app.api.v1.auctions.auction_service.get_user_bid", new=AsyncMock(return_value=None)
            ),
        ):
            response = client.get("/api/v1/auctions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["title"], "Лот")

    def test_read_auction_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/auctions/999")
        self.assertEqual(response.status_code, 404)

    def test_place_bid_rejects_non_positive_amount(self) -> None:
        session = SimpleNamespace()
        app = _build_app(_participant(), session)
        client = TestClient(app)
        response = client.post("/api/v1/auctions/1/bid", json={"amount": 0})
        self.assertEqual(response.status_code, 422)

    def test_place_bid_maps_value_error_to_409(self) -> None:
        auction = _auction()
        session = SimpleNamespace(get=AsyncMock(return_value=auction))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.auctions.auction_service.place_bid",
            new=AsyncMock(side_effect=ValueError("bid_too_low")),
        ):
            response = client.post("/api/v1/auctions/1/bid", json={"amount": 50})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "bid_too_low")

    def test_place_bid_success(self) -> None:
        auction = _auction()
        session = SimpleNamespace(get=AsyncMock(return_value=auction))
        app = _build_app(_participant(), session)
        client = TestClient(app)
        with (
            patch("app.api.v1.auctions.auction_service.place_bid", new=AsyncMock()),
            patch(
                "app.api.v1.auctions.auction_service.top_bid_with_user",
                new=AsyncMock(return_value=(None, None)),
            ),
            patch(
                "app.api.v1.auctions.auction_service.get_user_bid", new=AsyncMock(return_value=None)
            ),
        ):
            response = client.post("/api/v1/auctions/1/bid", json={"amount": 100})
        self.assertEqual(response.status_code, 200)


def _admin(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, telegram_id=555, role="admin", is_blocked=False, is_archived=False, permission_grants=[]
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_admin_app(user, session: SimpleNamespace, bot=None) -> FastAPI:
    from app.api.deps import get_bot, get_settings

    app = FastAPI()
    app.include_router(api_router)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    app.dependency_overrides[get_bot] = lambda: bot
    return app


class AdminAuctionsApiTests(unittest.TestCase):
    def test_participant_forbidden(self) -> None:
        session = SimpleNamespace()
        app = _build_admin_app(_participant(), session)
        client = TestClient(app)
        response = client.get("/api/v1/admin/auctions")
        self.assertEqual(response.status_code, 403)

    def test_create_auction_requires_future_end_time(self) -> None:
        session = SimpleNamespace()
        app = _build_admin_app(_admin(), session)
        client = TestClient(app)
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        response = client.post(
            "/api/v1/admin/auctions",
            json={"title": "T", "description": "d", "minimum_bid": 10, "bid_step": 5, "ends_at": past},
        )
        self.assertEqual(response.status_code, 422)

    def test_create_auction_success(self) -> None:
        auction = _auction()
        session = SimpleNamespace()
        app = _build_admin_app(_admin(), session)
        client = TestClient(app)
        future = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
        with (
            patch(
                "app.api.v1.admin.auction_service.create_auction", new=AsyncMock(return_value=auction)
            ),
            patch("app.api.v1.admin.auction_service.list_bids", new=AsyncMock(return_value=[])),
            patch(
                "app.api.v1.admin.auction_service.top_bid_with_user",
                new=AsyncMock(return_value=(None, None)),
            ),
        ):
            response = client.post(
                "/api/v1/admin/auctions",
                json={"title": "T", "description": "d", "minimum_bid": 10, "bid_step": 5, "ends_at": future},
            )
        self.assertEqual(response.status_code, 200)

    def test_confirm_winner_requires_bidding_closed(self) -> None:
        auction = _auction(status="active")
        session = SimpleNamespace(get=AsyncMock(return_value=auction))
        app = _build_admin_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/auctions/1/confirm-winner")
        self.assertEqual(response.status_code, 409)

    def test_confirm_winner_no_valid_bidder(self) -> None:
        auction = _auction(status="active", ends_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        session = SimpleNamespace(get=AsyncMock(return_value=auction))
        app = _build_admin_app(_admin(), session)
        client = TestClient(app)
        with patch(
            "app.api.v1.admin.auction_service.confirm_winner", new=AsyncMock(return_value=None)
        ):
            response = client.post("/api/v1/admin/auctions/1/confirm-winner")
        self.assertEqual(response.status_code, 409)

    def test_confirm_winner_success_notifies_winner(self) -> None:
        auction = _auction(status="active", ends_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        winner = SimpleNamespace(telegram_id=999)
        bid = SimpleNamespace(amount=200)
        session = SimpleNamespace(get=AsyncMock(return_value=auction))
        bot = SimpleNamespace()
        app = _build_admin_app(_admin(), session, bot=bot)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.admin.auction_service.confirm_winner",
                new=AsyncMock(return_value=(bid, winner)),
            ),
            patch("app.api.v1.admin.auction_service.list_bids", new=AsyncMock(return_value=[])),
            patch(
                "app.api.v1.admin.auction_service.top_bid_with_user",
                new=AsyncMock(return_value=(None, None)),
            ),
            patch("app.api.v1.admin.safe_send", new=AsyncMock()) as safe_send_mock,
        ):
            response = client.post("/api/v1/admin/auctions/1/confirm-winner")
        self.assertEqual(response.status_code, 200)
        safe_send_mock.assert_awaited_once()

    def test_deliver_requires_completed_status(self) -> None:
        auction = _auction(status="active")
        session = SimpleNamespace(get=AsyncMock(return_value=auction))
        app = _build_admin_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/auctions/1/deliver")
        self.assertEqual(response.status_code, 409)

    def test_cancel_requires_bidding_closed(self) -> None:
        auction = _auction(status="active")
        session = SimpleNamespace(get=AsyncMock(return_value=auction))
        app = _build_admin_app(_admin(), session)
        client = TestClient(app)
        response = client.post("/api/v1/admin/auctions/1/cancel")
        self.assertEqual(response.status_code, 409)

    def test_cancel_success(self) -> None:
        auction = _auction(status="active", ends_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        session = SimpleNamespace(get=AsyncMock(return_value=auction))
        app = _build_admin_app(_admin(), session)
        client = TestClient(app)
        with (
            patch("app.api.v1.admin.auction_service.cancel_auction", new=AsyncMock()),
            patch("app.api.v1.admin.auction_service.list_bids", new=AsyncMock(return_value=[])),
            patch(
                "app.api.v1.admin.auction_service.top_bid_with_user",
                new=AsyncMock(return_value=(None, None)),
            ),
        ):
            response = client.post("/api/v1/admin/auctions/1/cancel")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
