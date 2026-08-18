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


class OpportunityFilterHelpersTests(unittest.TestCase):
    """DELTA ToR §16-17: pure-function coverage for the real multi-facet
    filter -- the bits that used to just hide already-loaded cards
    client-side (see docs/DELTA ToR) now live server-side here."""

    def test_matches_facets_filters_by_issuer_type_and_category(self) -> None:
        from app.api.v1.opportunities import _matches_facets

        offer = _offer(opportunity_type="certificate", category="projects")
        partner = _partner(name="ЭРА")

        self.assertTrue(_matches_facets(offer, partner, issuer=None, otype=None, category=None))
        self.assertTrue(_matches_facets(offer, partner, issuer="ЭРА", otype="certificate", category="projects"))
        self.assertFalse(_matches_facets(offer, partner, issuer="Другой", otype=None, category=None))
        self.assertFalse(_matches_facets(offer, partner, issuer=None, otype="letter", category=None))
        self.assertFalse(_matches_facets(offer, partner, issuer=None, otype=None, category="events"))

    def test_compute_state_prioritizes_application_status(self) -> None:
        from app.api.v1.opportunities import _compute_state

        self.assertEqual(
            _compute_state(offer_open=True, application_status="issued", eligible=True, missing_requirements=[]),
            "issued",
        )
        self.assertEqual(
            _compute_state(offer_open=True, application_status="pending", eligible=False, missing_requirements=["Баллы"]),
            "requested",
        )
        self.assertEqual(
            _compute_state(offer_open=True, application_status="partner_review", eligible=True, missing_requirements=[]),
            "review",
        )

    def test_compute_state_available_almost_and_closed(self) -> None:
        from app.api.v1.opportunities import _compute_state

        self.assertEqual(
            _compute_state(offer_open=True, application_status=None, eligible=True, missing_requirements=[]),
            "available",
        )
        self.assertEqual(
            _compute_state(offer_open=True, application_status=None, eligible=False, missing_requirements=["Баллы"]),
            "almost",
        )
        self.assertEqual(
            _compute_state(offer_open=True, application_status=None, eligible=False, missing_requirements=["Баллы", "Ранг"]),
            "closed",
        )
        self.assertEqual(
            _compute_state(offer_open=False, application_status=None, eligible=True, missing_requirements=[]),
            "closed",
        )

    def test_sort_opportunities_by_organization_and_newest(self) -> None:
        from app.api.v1.opportunities import OpportunityOut, _sort_opportunities

        def _out(**overrides) -> OpportunityOut:
            defaults = dict(
                id=1, partner_name="B", title="Z", description="d", point_cost=0,
                required_points=0, opportunity_type="certificate", category=None,
                min_rank=None, eligible=True, default_award_wording=None,
                partner_review_required=False, remaining_slots="unlimited",
                expires_at=None, instruction=None, source_url=None,
                application_status=None, is_saved=False, is_offer_open=True,
                state="available",
            )
            defaults.update(overrides)
            return OpportunityOut(**defaults)

        a = _out(id=1, partner_name="Alpha", title="Second")
        b = _out(id=2, partner_name="Beta", title="First")

        by_org = _sort_opportunities([b, a], "by_organization")
        self.assertEqual([item.partner_name for item in by_org], ["Alpha", "Beta"])

        by_newest = _sort_opportunities([a, b], "newest")
        self.assertEqual([item.id for item in by_newest], [2, 1])


if __name__ == "__main__":
    unittest.main()
