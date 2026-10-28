"""Media deadline stages use durable keys and never burst stale reminders."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.services.media_service import _send_media_deadline_notice


class MediaDeadlineStageTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)
        self.settings = SimpleNamespace(timezone="Asia/Yerevan", media_deadline_3h_enabled=True)
        self.bot = object()
        self.session = object()

    def task(self, hours):
        return SimpleNamespace(
            id=81, title="Подготовить интервью",
            deadline=self.now + timedelta(hours=hours),
        )

    async def test_24h_window_sends_only_24h_stage(self):
        with patch("app.services.media_service._send_media_chat_notice",
                   new=AsyncMock(return_value=True)) as send:
            result = await _send_media_deadline_notice(
                self.session, self.bot, self.settings, self.task(12), self.now,
            )
        self.assertTrue(result)
        self.assertEqual(send.await_count, 1)
        self.assertEqual(send.await_args.kwargs["notice_kind"], "deadline_24h")
        self.assertEqual(send.await_args.kwargs["notice_key"],
                         f"task-24h:81:{self.task(12).deadline.isoformat()}")

    async def test_urgent_window_sends_only_3h_not_stale_24h(self):
        with patch("app.services.media_service._send_media_chat_notice",
                   new=AsyncMock(return_value=True)) as send:
            result = await _send_media_deadline_notice(
                self.session, self.bot, self.settings, self.task(2), self.now,
            )
        self.assertTrue(result)
        self.assertEqual(send.await_count, 1)
        self.assertEqual(send.await_args.kwargs["notice_kind"], "deadline_3h")
        self.assertIn("меньше 3 часов", send.await_args.kwargs["text"])

    async def test_disabled_flag_preserves_existing_24h_behavior(self):
        self.settings.media_deadline_3h_enabled = False
        with patch("app.services.media_service._send_media_chat_notice",
                   new=AsyncMock(return_value=True)) as send:
            result = await _send_media_deadline_notice(
                self.session, self.bot, self.settings, self.task(2), self.now,
            )
        self.assertTrue(result)
        self.assertEqual(send.await_count, 1)
        self.assertEqual(send.await_args.kwargs["notice_kind"], "deadline_24h")
        self.assertEqual(
            send.await_args.kwargs["notice_key"],
            f"task-24h:81:{self.task(2).deadline.isoformat()}",
        )

    async def test_stage_keys_are_distinct_and_stable_for_restart(self):
        task = self.task(12)
        with patch("app.services.media_service._send_media_chat_notice",
                   new=AsyncMock(return_value=True)) as send:
            await _send_media_deadline_notice(self.session, self.bot, self.settings, task, self.now)
            await _send_media_deadline_notice(self.session, self.bot, self.settings, task,
                                              self.now + timedelta(hours=10))
            await _send_media_deadline_notice(self.session, self.bot, self.settings, task,
                                              self.now + timedelta(hours=10))
        keys = [call.kwargs["notice_key"] for call in send.await_args_list]
        self.assertEqual(keys, [
            f"task-24h:81:{task.deadline.isoformat()}",
            f"task-3h:81:{task.deadline.isoformat()}",
            f"task-3h:81:{task.deadline.isoformat()}",
        ])
        # The unchanged key is deduplicated by the existing DB notice/receipt layer.

    async def test_expired_or_distant_tasks_do_not_send(self):
        with patch("app.services.media_service._send_media_chat_notice",
                   new=AsyncMock()) as send:
            for hours in (-1, 0, 25):
                self.assertFalse(await _send_media_deadline_notice(
                    self.session, self.bot, self.settings, self.task(hours), self.now,
                ))
            self.assertFalse(await _send_media_deadline_notice(
                self.session, self.bot, self.settings,
                SimpleNamespace(id=81, title="Нет срока", deadline=None), self.now,
            ))
        send.assert_not_awaited()

    async def test_exact_boundaries_and_naive_utc_compatibility(self):
        with patch("app.services.media_service._send_media_chat_notice",
                   new=AsyncMock(return_value=True)) as send:
            for hours in (24, 3):
                task = self.task(hours)
                task.deadline = task.deadline.replace(tzinfo=None)
                self.assertTrue(await _send_media_deadline_notice(
                    self.session, self.bot, self.settings, task, self.now,
                ))
        self.assertEqual([c.kwargs["notice_kind"] for c in send.await_args_list],
                         ["deadline_24h", "deadline_3h"])
