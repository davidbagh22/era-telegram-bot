"""Malformed reminder configurations are skipped as a whole."""
import unittest
from app.services.event_custom_reminder_service import _configured_thresholds


class ConfiguredReminderThresholdTests(unittest.TestCase):
    def test_valid_thresholds_preserve_existing_integer_semantics(self):
        self.assertEqual(_configured_thresholds([1440, "60", 60, 15, 0, -1, " +30 "]), [15, 30, 60, 1440])

    def test_malformed_record_never_activates_partial_intent(self):
        for invalid in (None, "", "broken", {}, [], True, False, 1.9, float("inf")):
            with self.subTest(invalid=invalid):
                self.assertEqual(_configured_thresholds([60, invalid, 30]), [])

    def test_bad_record_does_not_stop_later_healthy_configuration(self):
        self.assertEqual([_configured_thresholds(v) for v in ([None], [60], ["broken"], [30])],
                         [[], [60], [], [30]])

    def test_no_new_horizon_policy(self):
        self.assertEqual(_configured_thresholds([525601]), [525601])

    def test_non_list_config_is_skipped(self):
        for value in (None, "", "1440", 1440, {"reminders": [30]}, (30,), []):
            with self.subTest(value=value):
                self.assertEqual(_configured_thresholds(value), [])

    def test_huge_string_conversion_does_not_crash(self):
        self.assertEqual(_configured_thresholds(["9" * 10000, 60]), [])
