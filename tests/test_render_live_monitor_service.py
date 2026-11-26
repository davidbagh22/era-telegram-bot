"""Isolated unit tests for #565 Render LIVE stale monitor alert path.

No network, no Telegram, no production mutations.
"""
from __future__ import annotations

import asyncio
import time
import unittest
import unittest.mock
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import render_live_monitor_service as monitor

MAIN = "a" * 40
OLD = "b" * 40
NOW = datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)


def _jobs(conclusion="success"):
    return [
        {
            "name": name,
            "status": "completed" if conclusion == "success" else "in_progress",
            "conclusion": conclusion if conclusion == "success" else None,
        }
        for name in monitor._lag_module().REQUIRED_JOBS
    ]


def _snapshot(*, live=OLD, minutes=50, main_deploy=None, ci="success"):
    deploys = [{"id": "old-live", "status": "live", "commit": {"id": live}}]
    if main_deploy:
        deploys.insert(0, {"id": "new-deploy", "status": main_deploy, "commit": {"id": MAIN}})
    completed_minute = 60 - minutes if minutes <= 60 else 0
    completed_hour = 7 if minutes <= 60 else 6
    return {
        "main_sha": MAIN,
        "observed_at": "2026-10-30T08:00:00Z",
        "ci": {
            "head_sha": MAIN,
            "jobs": _jobs(ci),
            "completed_at": f"2026-10-30T{completed_hour:02d}:{completed_minute:02d}:00Z",
        },
        "deploys": deploys,
    }


class AlertDecisionTests(unittest.TestCase):
    def test_stale_pending_failed_healthy_exact_live(self):
        cases = (
            (_snapshot(), "STALE_LIVE", True),
            (_snapshot(minutes=10), "DEPLOY_PENDING", False),
            (_snapshot(main_deploy="build_failed"), "DEPLOY_FAILED", True),
            (_snapshot(live=MAIN), "LIVE", False),
        )
        for data, expected_status, alertable in cases:
            with self.subTest(expected_status=expected_status):
                result = monitor.classify_snapshot(data, now=NOW)
                self.assertEqual(result["status"], expected_status)
                self.assertEqual(monitor.should_alert(result["status"]), alertable)

    def test_rolled_back_is_alertable(self):
        result = monitor.classify_snapshot(
            _snapshot(main_deploy="deactivated"), now=NOW
        )
        self.assertEqual(result["status"], "ROLLED_BACK")
        self.assertTrue(monitor.should_alert(result["status"]))

    def test_ci_pending_and_failed_are_not_stale_alerts(self):
        pending = _snapshot(live=MAIN)
        pending["ci"]["jobs"][0]["status"] = "in_progress"
        pending["ci"]["jobs"][0]["conclusion"] = None
        pending_result = monitor.classify_snapshot(pending, now=NOW)
        self.assertEqual(pending_result["status"], "CI_PENDING")
        self.assertFalse(monitor.should_alert(pending_result["status"]))

        failed = _snapshot(live=MAIN)
        failed["ci"]["jobs"][0]["conclusion"] = "failure"
        failed_result = monitor.classify_snapshot(failed, now=NOW)
        self.assertEqual(failed_result["status"], "CI_FAILED")
        self.assertFalse(monitor.should_alert(failed_result["status"]))


class AlertFormattingTests(unittest.TestCase):
    def test_ops_message_includes_shas_without_secrets(self):
        result = {
            "status": "STALE_LIVE",
            "reason": "CI green but exact main not LIVE within release SLO",
            "main_sha": MAIN,
            "live_sha": OLD,
            "minutes_since_green_ci": 50,
            "latest_main_deploy_id": "dep-test",
        }
        text = monitor.format_ops_alert(result)
        self.assertIn(MAIN, text)
        self.assertIn(OLD, text)
        self.assertIn("STALE_LIVE", text)
        self.assertIn("50", text)
        self.assertNotIn("token=", text.lower())
        self.assertNotIn("Bearer", text)
        self.assertEqual(
            monitor.durable_alert_key(result),
            f"render-live-stale:STALE_LIVE:{MAIN}:{OLD}",
        )


class ProcessSnapshotTests(unittest.TestCase):
    def test_builds_exact_live_snapshot_from_github_and_process_sha(self):
        completed = "2026-10-30T07:00:00Z"

        def fetch(url: str):
            if url.endswith("/branches/main"):
                return {"commit": {"sha": MAIN}}
            if "/actions/runs?" in url:
                return {
                    "workflow_runs": [
                        {
                            "id": 9,
                            "name": "Bot checks",
                            "event": "push",
                            "head_sha": MAIN,
                            "created_at": completed,
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ]
                }
            if "/actions/runs/9/jobs?" in url:
                return {
                    "jobs": [
                        {
                            "name": name,
                            "status": "completed",
                            "conclusion": "success",
                            "completed_at": completed,
                        }
                        for name in monitor._lag_module().REQUIRED_JOBS
                    ]
                }
            raise AssertionError(url)

        snapshot = monitor.build_live_process_snapshot(
            fetch, live_sha=OLD, observed_at=NOW
        )
        result = monitor.classify_snapshot(snapshot, now=NOW)
        self.assertEqual(result["status"], "STALE_LIVE")
        self.assertEqual(result["live_sha"], OLD)

    def test_rejects_seven_char_live_prefix(self):
        with self.assertRaises(ValueError):
            monitor.build_live_process_snapshot(lambda url: {}, live_sha="a" * 7)


class NotifyGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_feature_off_skips_admin_dm(self):
        settings = SimpleNamespace(feature_render_live_stale_alerts="OFF")
        result = {
            "status": "STALE_LIVE",
            "reason": "lag",
            "main_sha": MAIN,
            "live_sha": OLD,
        }
        notify = AsyncMock()
        outcome = await monitor.maybe_notify_stale_live(
            AsyncMock(), settings, result, notify_once=notify
        )
        self.assertFalse(outcome["alerted"])
        self.assertEqual(outcome["skipped_reason"], "feature_disabled")
        notify.assert_not_called()

    async def test_feature_on_uses_durable_key(self):
        settings = SimpleNamespace(feature_render_live_stale_alerts="ALL")
        result = {
            "status": "STALE_LIVE",
            "reason": "lag",
            "main_sha": MAIN,
            "live_sha": OLD,
            "minutes_since_green_ci": 50,
        }
        notify = AsyncMock(return_value=(1, 0, 0))
        outcome = await monitor.maybe_notify_stale_live(
            AsyncMock(), settings, result, notify_once=notify
        )
        self.assertTrue(outcome["alerted"])
        self.assertEqual(outcome["sent"], 1)
        kwargs = notify.await_args.kwargs
        self.assertEqual(
            kwargs["delivery_key"], f"render-live-stale:STALE_LIVE:{MAIN}:{OLD}"
        )
        self.assertEqual(kwargs["notification_type"], "render_live_stale")

    async def test_pending_does_not_notify_even_when_enabled(self):
        settings = SimpleNamespace(feature_render_live_stale_alerts="ALL")
        notify = AsyncMock()
        outcome = await monitor.maybe_notify_stale_live(
            AsyncMock(),
            settings,
            {"status": "DEPLOY_PENDING", "main_sha": MAIN, "live_sha": OLD},
            notify_once=notify,
        )
        self.assertEqual(outcome["skipped_reason"], "status_not_alertable")
        notify.assert_not_called()


class SchedulerEntryTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_render_skips_without_network(self):
        settings = SimpleNamespace(
            is_render_deployment=False,
            feature_render_live_stale_alerts="OFF",
        )
        result = await monitor.run_render_live_monitor(AsyncMock(), settings)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["reason"], "not_render_deployment")


class EventLoopNonBlockingTests(unittest.IsolatedAsyncioTestCase):
    def _settings(self):
        return SimpleNamespace(
            is_render_deployment=True,
            feature_render_live_stale_alerts="OFF",
        )

    async def test_blocking_snapshot_builder_does_not_block_event_loop(self):
        def blocking_builder(fetch, *, live_sha, observed_at):
            time.sleep(0.15)
            return _snapshot(live=live_sha, minutes=10)

        beats: list[float] = []
        started = time.monotonic()

        async def heartbeat():
            await asyncio.sleep(0.01)
            beats.append(time.monotonic() - started)

        with unittest.mock.patch.object(monitor, "current_commit_sha", return_value=OLD):
            monitor_task = asyncio.create_task(
                monitor.run_render_live_monitor(
                    AsyncMock(),
                    self._settings(),
                    snapshot_builder=blocking_builder,
                    now=NOW,
                )
            )
            await heartbeat()
            self.assertEqual(len(beats), 1)
            self.assertLess(beats[0], 0.1)
            self.assertFalse(monitor_task.done())
            result = await monitor_task
        self.assertGreaterEqual(time.monotonic() - started, 0.15)
        self.assertEqual(result["status"], "DEPLOY_PENDING")

    async def test_async_snapshot_builder_is_awaited(self):
        async def async_builder(fetch, *, live_sha, observed_at):
            return _snapshot(live=live_sha, minutes=10)

        with unittest.mock.patch.object(monitor, "current_commit_sha", return_value=OLD):
            result = await monitor.run_render_live_monitor(
                AsyncMock(), self._settings(), snapshot_builder=async_builder, now=NOW
            )
        self.assertEqual(result["status"], "DEPLOY_PENDING")


if __name__ == "__main__":
    unittest.main()
