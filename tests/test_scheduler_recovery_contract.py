"""Guard critical recovery scheduler wiring without running jobs or Telegram.

These are structural checks only. They do not establish delivery, catch-up,
PostgreSQL fault tolerance or real Telegram acceptance.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.system_scheduler import add_system_jobs


class _RecordingScheduler:
    def __init__(self):
        self.jobs = {}

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def remove_job(self, job_id):
        self.jobs.pop(job_id, None)

    def add_job(self, callback, trigger, **kwargs):
        job_id = kwargs["id"]
        if job_id in self.jobs:
            raise AssertionError(f"Duplicate scheduler job: {job_id}")
        self.jobs[job_id] = (callback, trigger, kwargs)


class SchedulerRecoveryContractTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = _RecordingScheduler()
        settings = SimpleNamespace(
            timezone="Asia/Yerevan",
            feature_management_reports="OFF",
        )
        with (
            patch("app.services.system_scheduler.source_targets", return_value={}),
            patch("app.services.system_scheduler.mark_coverage_gap"),
        ):
            add_system_jobs(self.scheduler, object(), settings, object())

    def test_critical_recovery_jobs_remain_bounded_and_coalesced(self):
        """No overlapping per-minute retry of a failing DB/Telegram job."""
        for job_id in (
            "event-announcement-recovery",
            "event-lifecycle-notifications",
            "event-wizard-task-sync",
            "configured-event-reminders",
            "project-review-notices",
            "application-notices",
            "media-channel-publication",
            "media-task-cards",
            "media-chat-automation",
            "admin-broadcast-resume",
        ):
            with self.subTest(job_id=job_id):
                _, trigger, options = self.scheduler.jobs[job_id]
                self.assertEqual(trigger, "interval")
                self.assertEqual(options["minutes"], 1)
                self.assertEqual(options["max_instances"], 1)
                self.assertTrue(options["coalesce"])
                self.assertTrue(options["replace_existing"])

    def test_event_announcement_and_wizard_recovery_run_after_restart(self):
        """On scheduler setup, these jobs are due without waiting a minute."""
        for job_id in ("event-announcement-recovery", "event-wizard-task-sync"):
            with self.subTest(job_id=job_id):
                _, _, options = self.scheduler.jobs[job_id]
                self.assertIsNotNone(options.get("next_run_time"))


if __name__ == "__main__":
    unittest.main()
