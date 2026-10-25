from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.auction_service import bidder_name, format_local, is_open, remaining_time


class AuctionTimingTests(unittest.TestCase):
    def test_remaining_time(self) -> None:
        now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(remaining_time(now + timedelta(hours=2, minutes=15), now), "2 ч. 15 мин.")
        self.assertEqual(remaining_time(now - timedelta(seconds=1), now), "завершён")

    def test_local_time_format(self) -> None:
        value = datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc)
        self.assertEqual(format_local(value, "Asia/Yerevan"), "12.07.2026 20:00")

    def test_bidder_name_contains_username(self) -> None:
        user = SimpleNamespace(first_name="Давид", last_name="Багдасарян", username="davidbagh22")
        self.assertEqual(bidder_name(user), "Давид Багдасарян (@davidbagh22)")

    def test_auction_closes_by_time(self) -> None:
        now = datetime.now(timezone.utc)
        auction = SimpleNamespace(status="active", starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1))
        self.assertTrue(is_open(auction, now))
        auction.ends_at = now - timedelta(seconds=1)
        self.assertFalse(is_open(auction, now))


if __name__ == "__main__":
    unittest.main()
