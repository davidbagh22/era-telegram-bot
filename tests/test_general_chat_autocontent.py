from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app.config import Settings
from app.services import general_chat_content_service as content
from app.services.scheduler_service import create_scheduler


class GeneralChatContentPackTests(unittest.TestCase):
    def test_every_calendar_day_has_both_prepared_quotes(self) -> None:
        day = date(2025, 1, 1)
        seen_morning: set[str] = set()
        seen_evening: set[str] = set()
        for _ in range(365):
            morning = content._quote_for(day, "morning")
            evening = content._quote_for(day, "evening")
            self.assertIsNotNone(morning)
            self.assertIsNotNone(evening)
            assert morning is not None and evening is not None
            seen_morning.add(morning.text)
            seen_evening.add(evening.text)
            day += timedelta(days=1)
        self.assertEqual(len(seen_morning), 365)
        self.assertEqual(len(seen_evening), 365)

    def test_sunday_challenge_stays_linked_to_that_month(self) -> None:
        sundays = [
            date(2026, 8, 16),
            date(2026, 12, 6),
            date(2027, 4, 4),
            date(2027, 8, 8),
        ]
        for sunday in sundays:
            challenge = content._weekly_challenge(sunday)
            self.assertIsNotNone(challenge)
            assert challenge is not None
            self.assertEqual(challenge.content_type, "weekly_challenge")
            self.assertEqual(sunday.weekday(), 6)

    def test_base_holiday_calendar_contains_expected_priority_date(self) -> None:
        holiday = content._static_holiday(date(2026, 1, 1))
        self.assertIsNotNone(holiday)
        assert holiday is not None
        self.assertEqual(holiday.content_type, "holiday")
        self.assertEqual(holiday.content_id, "holiday-0101")

    def test_idempotency_key_is_deterministic(self) -> None:
        key = content.scheduled_idempotency_key(date(2026, 8, 16), "evening", "weekly_challenge")
        self.assertEqual(
            key,
            "general_content:2026-08-16:evening:weekly_challenge",
        )

    def test_quote_more_than_hour_late_is_skipped(self) -> None:
        item = content.ContentItem(
            content_id="morning-0816",
            content_type="morning_quote",
            slot="morning",
            text="test",
        )
        zone = ZoneInfo("Asia/Yerevan")
        planned = datetime(2026, 8, 16, 9, 0, tzinfo=zone)
        self.assertEqual(
            content._late_status(item, planned, planned + timedelta(minutes=61)),
            "skipped_late",
        )
        self.assertIsNone(
            content._late_status(item, planned, planned + timedelta(minutes=60))
        )

    def test_significant_content_expires_after_six_hours(self) -> None:
        item = content.ContentItem(
            content_id="challenge-01",
            content_type="weekly_challenge",
            slot="evening",
            text="test",
        )
        zone = ZoneInfo("Asia/Yerevan")
        planned = datetime(2026, 8, 16, 18, 0, tzinfo=zone)
        self.assertEqual(
            content._late_status(item, planned, planned + timedelta(hours=6, seconds=1)),
            "missed",
        )
        self.assertIsNone(content._late_status(item, planned, planned + timedelta(hours=6)))


class GeneralChatPriorityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        content.clear_content_cache()
        self.session = SimpleNamespace()

    async def test_holiday_precedes_monthly_theme_and_quote(self) -> None:
        flags = {
            "paused": False,
            "quotes": True,
            "challenges": True,
            "themes": True,
            "holidays": True,
        }
        holiday = content._static_holiday(date(2026, 1, 1))
        self.assertIsNotNone(holiday)
        with (
            patch.object(content, "get_autocontent_settings", new=AsyncMock(return_value=flags)),
            patch.object(content, "_custom_holiday", new=AsyncMock(return_value=None)),
            patch.object(content, "_theme_due_today", new=AsyncMock(return_value=True)),
            patch.object(
                content,
                "_override_resolution",
                new=AsyncMock(side_effect=lambda _session, item: content._CandidateResolution(item=item)),
            ),
        ):
            planned = await content.plan_content(
                self.session,
                date(2026, 1, 1),
                "morning",
                timezone_name="Asia/Yerevan",
            )
        self.assertIsNotNone(planned)
        assert planned is not None
        self.assertEqual(planned.item.content_type, "holiday")

    async def test_monthly_theme_precedes_morning_quote_on_free_morning(self) -> None:
        flags = {
            "paused": False,
            "quotes": True,
            "challenges": True,
            "themes": True,
            "holidays": True,
        }
        with (
            patch.object(content, "get_autocontent_settings", new=AsyncMock(return_value=flags)),
            patch.object(content, "_custom_holiday", new=AsyncMock(return_value=None)),
            patch.object(content, "_theme_due_today", new=AsyncMock(return_value=True)),
            patch.object(
                content,
                "_override_resolution",
                new=AsyncMock(side_effect=lambda _session, item: content._CandidateResolution(item=item)),
            ),
        ):
            planned = await content.plan_content(
                self.session,
                date(2026, 1, 2),
                "morning",
                timezone_name="Asia/Yerevan",
            )
        self.assertIsNotNone(planned)
        assert planned is not None
        self.assertEqual(planned.item.content_type, "monthly_theme")

    async def test_sunday_challenge_replaces_evening_quote(self) -> None:
        flags = {
            "paused": False,
            "quotes": True,
            "challenges": True,
            "themes": True,
            "holidays": True,
        }
        with (
            patch.object(content, "get_autocontent_settings", new=AsyncMock(return_value=flags)),
            patch.object(
                content,
                "_override_resolution",
                new=AsyncMock(side_effect=lambda _session, item: content._CandidateResolution(item=item)),
            ),
        ):
            planned = await content.plan_content(
                self.session,
                date(2026, 8, 16),
                "evening",
                timezone_name="Asia/Yerevan",
            )
        self.assertIsNotNone(planned)
        assert planned is not None
        self.assertEqual(planned.item.content_type, "weekly_challenge")

    async def test_paused_system_produces_no_content(self) -> None:
        flags = {
            "paused": True,
            "quotes": True,
            "challenges": True,
            "themes": True,
            "holidays": True,
        }
        with patch.object(
            content, "get_autocontent_settings", new=AsyncMock(return_value=flags)
        ):
            planned = await content.plan_content(
                self.session,
                date(2026, 8, 16),
                "morning",
                timezone_name="Asia/Yerevan",
            )
        self.assertIsNone(planned)


class GeneralChatDeliverySafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_unbound_general_chat_never_falls_back_to_another_chat(self) -> None:
        zone = ZoneInfo("Asia/Yerevan")
        now = datetime(2026, 8, 16, 9, 0, tzinfo=zone)
        item = content.ContentItem(
            content_id="morning-0816",
            content_type="morning_quote",
            slot="morning",
            text="test",
        )
        planned = content.PlannedContent(item=item, planned_at=now, effective_text=item.text)
        delivery = SimpleNamespace(
            id=5,
            status="claimed",
            content_id=item.content_id,
            telegram_message_id=None,
            attempts=0,
            chat_id=None,
            error_code=None,
            error_detail=None,
            sent_at=None,
        )
        session = SimpleNamespace(commit=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        settings = Settings(bot_token="0000000000:TESTTOKEN", timezone="Asia/Yerevan")
        with (
            patch.object(content, "_claim_delivery", new=AsyncMock(return_value=(delivery, True))),
            patch.object(content, "_general_chat_id", new=AsyncMock(return_value=None)),
            patch.object(content, "_alert_delivery_failure", new=AsyncMock()) as alert,
        ):
            outcome = await content.deliver_planned_content(
                bot, settings, session, planned, now=now
            )
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(delivery.error_code, "general_chat_unbound")
        bot.send_message.assert_not_awaited()
        alert.assert_awaited_once()


class GeneralChatSchedulerTests(unittest.TestCase):
    def test_scheduler_has_two_slots_and_recovery_without_legacy_general_nudge(self) -> None:
        settings = Settings(bot_token="0000000000:TESTTOKEN", timezone="Asia/Yerevan")
        bot = SimpleNamespace()
        scheduler = create_scheduler(bot, settings, lambda: None)
        jobs = {job.id: job for job in scheduler.get_jobs()}
        self.assertIn("general-content-morning", jobs)
        self.assertIn("general-content-evening", jobs)
        self.assertIn("general-content-recovery", jobs)
        self.assertNotIn("weekly-general", jobs)
        self.assertEqual(str(scheduler.timezone), "Asia/Yerevan")


if __name__ == "__main__":
    unittest.main()
