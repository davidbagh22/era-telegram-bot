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
