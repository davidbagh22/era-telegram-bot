"""No Telegram side effects: legacy event activity deadline normalization."""
import unittest
from datetime import datetime, timedelta, timezone
from app.handlers.participant.events import _activity_expired


class EventActivityDeadlineTimezoneTests(unittest.TestCase):
    def test_unbounded_activity_is_open(self):
        self.assertFalse(_activity_expired(None))

    def test_naive_utc_legacy_timestamp(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(_activity_expired((now - timedelta(days=1)).replace(tzinfo=None)))
        self.assertFalse(_activity_expired((now + timedelta(days=1)).replace(tzinfo=None)))

    def test_aware_yerevan_timezone_preserves_instant(self):
        offset = timezone(timedelta(hours=4))
        now = datetime.now(timezone.utc)
        self.assertTrue(_activity_expired((now - timedelta(days=1)).astimezone(offset)))
        self.assertFalse(_activity_expired((now + timedelta(days=1)).astimezone(offset)))
