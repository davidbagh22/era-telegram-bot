"""Opportunities hub should lead with ranks/leaderboard, not locked teasers."""
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]


class OpportunitiesRanksHubTests(TestCase):
    def test_opportunities_screen_embeds_ranks_panel(self) -> None:
        source = (ROOT / "frontend/src/screens/OpportunitiesScreen.tsx").read_text(encoding="utf-8")
        self.assertIn("RanksPanel", source)
        self.assertIn("Открытые предложения", source)
        # Preserve stored null (e.g. «Все») — do not coerce with ?? "available".
        self.assertIn('if (!stored) return "available"', source)
        self.assertIn("const value = stored.status", source)

    def test_opportunity_deep_link_uses_all_scope_not_mine(self) -> None:
        """Growth regression: Home / cert ladder deep-links must open apply cards.

        Scope «mine» only lists existing applications, so an unapplied
        `#/opportunities/{id}` offer never appears and the CTA is a dead end.
        """
        source = (ROOT / "frontend/src/screens/OpportunitiesScreen.tsx").read_text(encoding="utf-8")
        self.assertIn('initialItemId ? "all"', source)
        self.assertNotIn('initialItemId ? "mine"', source)
        self.assertIn("setExpandedId(initialItemId)", source)
        self.assertIn('id="opportunities-offers"', source)
        # Session category (e.g. events) must not hide public_activity certs.
        self.assertIn("setCategory(null)", source)
        self.assertIn('initialItemId ? null : stored?.category', source)
        # Inactive/expired applications from admin notifications: mine then by-id.
        self.assertIn('scope: "mine"', source)
        self.assertIn("fetchOpportunity(initialItemId)", source)
        self.assertIn("deepLinkOffer", source)

    def test_certificates_ladder_resolves_offer_not_same_hash(self) -> None:
        source = (ROOT / "frontend/src/screens/opportunities/CertificatesPanel.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("fetchOpportunities", source)
        self.assertIn("openCertificateApplication", source)
        self.assertIn("`#/opportunities/${match.id}`", source)
        self.assertNotIn('window.location.hash = "#/opportunities";', source)
        self.assertIn("Сертификат участника ЭРА", source)
        self.assertIn("Дом Москвы в Ереване", source)

    def test_ranks_panel_covers_ladder_and_points_board(self) -> None:
        source = (ROOT / "frontend/src/screens/opportunities/RanksPanel.tsx").read_text(encoding="utf-8")
        self.assertIn("Лестница рангов", source)
        self.assertIn("Рейтинг по баллам", source)
        self.assertIn("active_member", source)
        self.assertIn("fetchLeaderboard", source)

    def test_home_afisha_uses_event_title_without_hardcoded_gathering(self) -> None:
        source = (ROOT / "frontend/src/screens/HomeScreen.tsx").read_text(encoding="utf-8")
        self.assertIn("{featuredEvent.title}", source)
        self.assertNotIn("Сбор в 17:30", source)
        self.assertNotIn("Первая годовщина ЭРА — 1 ГОД", source)
        self.assertIn("upcomingEvents.slice(0, 3)", source)
