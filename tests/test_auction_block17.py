from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AuctionFlowContractTests(unittest.TestCase):
    def test_participant_flow_uses_row_lock_and_balance_check(self) -> None:
        source = (ROOT / "app/handlers/participant/auction_block17.py").read_text(encoding="utf-8")
        self.assertIn("with_for_update", source)
        self.assertIn("total_points", source)
        self.assertIn("Баллы пока не списаны", source)
        self.assertIn('callback_data="auctions:list"', (ROOT / "app/handlers/participant/navigation.py").read_text(encoding="utf-8"))

    def test_admin_confirms_winner_before_points_are_spent(self) -> None:
        source = (ROOT / "app/handlers/admin/auction_block17.py").read_text(encoding="utf-8")
        self.assertIn('points=-winner_bid.amount', source)
        self.assertIn('winner_bid.status = "winner"', source)
        self.assertIn('auction.status = "completed"', source)
        self.assertIn("with_for_update", source)

    def test_routers_are_registered(self) -> None:
        participant = (ROOT / "app/handlers/participant/__init__.py").read_text(encoding="utf-8")
        admin = (ROOT / "app/handlers/admin/__init__.py").read_text(encoding="utf-8")
        self.assertIn("auction_block17.router", participant)
        self.assertIn("auction_block17.router", admin)


if __name__ == "__main__":
    unittest.main()
