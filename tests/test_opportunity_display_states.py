from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.v1.opportunities import _display_state, _to_opportunity_out


class OpportunityDisplayStateTests(unittest.IsolatedAsyncioTestCase):
    def _offer(self, **overrides):
        defaults = dict(
            id=1,
            title="Opportunity",
            description="Description",
            point_cost=100,
            opportunity_type="certificate",
            min_rank=None,
            default_award_wording=None,
            partner_review_required=False,
            expires_at=None,
            instruction=None,
            source_url=None,
            created_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_recognition_offer_is_almost_only_with_one_missing_requirement(self) -> None:
        offer = self._offer()
        self.assertEqual(
            _display_state(offer, eligible=False, missing_requirements=["Баллы"]),
            "almost",
        )
        self.assertEqual(
            _display_state(
                offer,
                eligible=False,
                missing_requirements=["Баллы", "Ранг"],
            ),
            "locked",
        )

    def test_recent_available_offer_is_new_but_future_timestamp_is_not(self) -> None:
        recent = self._offer(created_at=datetime.now(timezone.utc) - timedelta(days=2))
        future = self._offer(created_at=datetime.now(timezone.utc) + timedelta(days=2))
        self.assertEqual(_display_state(recent, eligible=True, missing_requirements=[]), "new")
        self.assertEqual(_display_state(future, eligible=True, missing_requirements=[]), "available")

    async def test_external_offer_is_locked_when_balance_is_below_real_redemption_cost(self) -> None:
        offer = self._offer(opportunity_type="external")
        partner = SimpleNamespace(name="Partner")
        user = SimpleNamespace(id=42)
        session = AsyncMock()

        with (
            patch("app.api.v1.opportunities.opportunity_service.get_application", new=AsyncMock(return_value=None)),
            patch("app.api.v1.opportunities.opportunity_service.remaining_slots", new=AsyncMock(return_value=None)),
            patch("app.api.v1.opportunities.opportunity_service.is_saved", new=AsyncMock(return_value=False)),
            patch("app.api.v1.opportunities.total_points", new=AsyncMock(return_value=50)),
        ):
            result = await _to_opportunity_out(session, offer, partner, user)

        self.assertFalse(result.eligible)
        self.assertEqual(result.display_state, "locked")
        self.assertEqual(result.missing_requirements, ["Баллы"])


if __name__ == "__main__":
    unittest.main()
