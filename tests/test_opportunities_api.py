from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings


def _user(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, telegram_id=555, first_name="Dev", last_name=None)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _offer(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=10,
        partner_id=1,
        title="Forum",
        description="d",
        point_cost=10,
        quantity=None,
        expires_at=None,
        instruction=None,
        source_url=None,
        is_active=True,
        is_archived=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _partner(**overrides) -> SimpleNamespace:
    defaults = dict(id=1, name="Acme")
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_app(session: SimpleNamespace, bot=None) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    # AsyncSession exposes scalar(); opportunity display-state calculation now
    # reads the user's real point balance, so API test doubles must model it.
    if not hasattr(session, "scalar"):
        session.scalar = AsyncMock(return_value=1000)

    async def _session_override():
        yield session

    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="1234567890:test-token")
    app.dependency_overrides[get_bot] = lambda: bot
    return app


def _session_for_offer(offer, partner) -> SimpleNamespace:
    async def _get(_model, obj_id):
        return offer if obj_id == offer.id else partner

    return SimpleNamespace(get=_get)


class OpportunitiesListApiTests(unittest.TestCase):
    def test_list_default_scope_uses_recommendations(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        item = SimpleNamespace(offer=_offer(), partner=_partner(), reasons=["доступно по вашему балансу баллов"])
        with (
            patch(
                "app.api.v1.opportunities.opportunity_service.recommended_offers",
                new=AsyncMock(return_value=[item]),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.get_application",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.remaining_slots",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.is_saved", new=AsyncMock(return_value=False)
            ),
        ):
            response = client.get("/api/v1/opportunities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["title"], "Forum")
        self.assertIn("доступно по вашему балансу баллов", body[0]["reasons"])

    def test_list_all_scope(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.opportunities.opportunity_service.list_active_offers",
                new=AsyncMock(return_value=[(_offer(), _partner())]),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.get_application",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.remaining_slots",
                new=AsyncMock(return_value=3),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.is_saved", new=AsyncMock(return_value=False)
            ),
        ):
            response = client.get("/api/v1/opportunities", params={"scope": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["remaining_slots"], "3")

    def test_list_saved_scope(self) -> None:
        session = SimpleNamespace()
        app = _build_app(session)
        client = TestClient(app)
        with (
            patch(
                "app.api.v1.opportunities.opportunity_service.list_saved_offers",
                new=AsyncMock(return_value=[(_offer(), _partner())]),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.get_application",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.remaining_slots",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.is_saved", new=AsyncMock(return_value=True)
            ),
        ):
            response = client.get("/api/v1/opportunities", params={"scope": "saved"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()[0]["is_saved"])

    def test_list_mine_scope(self) -> None:
        offer = _offer()
        partner = _partner()
        session = SimpleNamespace(get=AsyncMock(return_value=partner))
        app = _build_app(session)
        client = TestClient(app)
        application = SimpleNamespace(status="pending", initiative_id=offer.id)
        with (
            patch(
                "app.api.v1.opportunities.opportunity_service.list_my_applications",
                new=AsyncMock(return_value=[(application, offer)]),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.get_application",
                new=AsyncMock(return_value=application),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.remaining_slots",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.is_saved", new=AsyncMock(return_value=False)
            ),
        ):
            response = client.get("/api/v1/opportunities", params={"scope": "mine"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["application_status"], "pending")


class OpportunityDetailApiTests(unittest.TestCase):
    def test_not_found_when_offer_missing(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(session)
        client = TestClient(app)
        response = client.get("/api/v1/opportunities/999")
        self.assertEqual(response.status_code, 404)


class OpportunityApplyApiTests(unittest.TestCase):
    def test_apply_success_notifies_admins_when_bot_available(self) -> None:
        offer = _offer()
        partner = _partner()
        session = _session_for_offer(offer, partner)
        bot = SimpleNamespace()
        app = _build_app(session, bot=bot)
        client = TestClient(app)
        application = SimpleNamespace(status="pending")
        with (
            patch(
                "app.api.v1.opportunities.opportunity_service.apply_to_offer",
                new=AsyncMock(return_value=(application, None)),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.get_application",
                new=AsyncMock(return_value=application),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.remaining_slots",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.is_saved", new=AsyncMock(return_value=False)
            ),
            patch("app.api.v1.opportunities.notify_admins", new=AsyncMock()) as notify_mock,
        ):
            response = client.post("/api/v1/opportunities/10/apply")
        self.assertEqual(response.status_code, 200)
        notify_mock.assert_awaited_once()

    def test_apply_conflict_insufficient_points(self) -> None:
        offer = _offer()
        partner = _partner()
        session = _session_for_offer(offer, partner)
        app = _build_app(session)
        client = TestClient(app)
        with patch(
            "app.api.v1.opportunities.opportunity_service.apply_to_offer",
            new=AsyncMock(return_value=(None, "insufficient_points")),
        ):
            response = client.post("/api/v1/opportunities/10/apply")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "insufficient_points")

    def test_apply_not_found(self) -> None:
        session = SimpleNamespace(get=AsyncMock(return_value=None))
        app = _build_app(session)
        client = TestClient(app)
        response = client.post("/api/v1/opportunities/999/apply")
        self.assertEqual(response.status_code, 404)


class OpportunitySaveApiTests(unittest.TestCase):
    def test_save_and_unsave(self) -> None:
        offer = _offer()
        partner = _partner()
        session = _session_for_offer(offer, partner)
        app = _build_app(session)
        client = TestClient(app)
        with (
            patch("app.api.v1.opportunities.opportunity_service.save_offer", new=AsyncMock()),
            patch("app.api.v1.opportunities.opportunity_service.unsave_offer", new=AsyncMock()),
            patch(
                "app.api.v1.opportunities.opportunity_service.get_application",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.remaining_slots",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api.v1.opportunities.opportunity_service.is_saved", new=AsyncMock(return_value=True)
            ),
        ):
            response = client.post("/api/v1/opportunities/10/save")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_saved"])


if __name__ == "__main__":
    unittest.main()
