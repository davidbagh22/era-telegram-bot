"""Legacy reminder JSON must not crash the whole scheduled reminder pass."""
import unittest

from app.services.event_custom_reminder_service import _configured_thresholds


class ConfiguredReminderThresholdTests(unittest.TestCase):
    def test_valid_positive_minutes_are_deduplicated_and_sorted(self):
        self.assertEqual(_configured_thresholds([1440, "60", 60, 15, 0, -1]), [15, 60, 1440])

    def test_invalid_legacy_values_are_ignored(self):
        self.assertEqual(
            _configured_thresholds([None, "", "broken", {}, [], True, False, float("inf"), 30]),
            [30],
        )

    def test_fractional_float_and_absurd_thresholds_never_activate_sends(self):
        self.assertEqual(
            _configured_thresholds([
                1.9, 60.0, "1.9", "1e3", float("nan"), 9999999999,
                "999999999999999999999999", -1, True, 60, "060", 525600, 525601,
            ]),
            [60, 525600],
        )

    def test_canonical_positive_legacy_integer_strings(self):
        self.assertEqual(_configured_thresholds([" 15 ", "1440", 60, "00030"]), [15, 30, 60, 1440])

    def test_non_list_or_empty_config_is_safe(self):
        for value in (None, "", "1440", 1440, {"reminders": [30]}, []):
            with self.subTest(value=value):
                self.assertEqual(_configured_thresholds(value), [])


if __name__ == "__main__":
    unittest.main()
