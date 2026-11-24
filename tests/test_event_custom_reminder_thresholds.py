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


class ConfiguredReminderPassTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_record_does_not_starve_healthy_receipted_record(self):
        from datetime import datetime, timedelta, timezone
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services import event_custom_reminder_service as service

        start = datetime.now(timezone.utc) + timedelta(hours=1)
        event = SimpleNamespace(
            id=2, title="Isolated test", event_date=start.date(),
            event_time=start.time(), location="Test",
        )
        rows = [
            (SimpleNamespace(id=1), event, SimpleNamespace(reminders=[None, 1440]), SimpleNamespace()),
            (SimpleNamespace(id=2), event, SimpleNamespace(reminders=[1440]), SimpleNamespace()),
        ]
        result = MagicMock()
        result.all.return_value = rows
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        session.scalar = AsyncMock(return_value=7)  # Existing personal-delivery receipt.
        session.commit = AsyncMock()
        session.__aenter__.return_value = session
        factory = MagicMock(return_value=session)
        with patch.object(service, "send_general_topic", new_callable=AsyncMock) as group, patch.object(
            service, "send_bot_notification", new_callable=AsyncMock
        ) as personal:
            await service.send_configured_event_reminders(
                SimpleNamespace(), SimpleNamespace(timezone="UTC"), factory
            )
        group.assert_awaited_once()
        session.scalar.assert_awaited_once()
        personal.assert_not_awaited()
        session.add.assert_not_called()
        session.commit.assert_awaited_once()
