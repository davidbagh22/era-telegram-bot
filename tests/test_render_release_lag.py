"""Offline regression tests for release lag classification (no API calls)."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_release_lag.py"
spec = importlib.util.spec_from_file_location("render_release_lag", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

MAIN = "a" * 40
OLD = "b" * 40
NOW = datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)


def snapshot(*, status="live", live=OLD, ci_status="success", ci_sha=MAIN, minutes=50, main_deploy=None):
    jobs = [{"name": name, "status": "completed" if ci_status == "success" else "in_progress", "conclusion": ci_status if ci_status == "success" else None} for name in module.REQUIRED_JOBS]
    deploys = [{"id": "old-live", "status": status, "commit": {"id": live}}]
    if main_deploy:
        deploys.insert(0, {"id": "new-deploy", "status": main_deploy, "commit": {"id": MAIN}})
    return {"main_sha": MAIN, "observed_at": "2026-10-30T08:00:00Z", "ci": {"head_sha": ci_sha, "jobs": jobs, "completed_at": f"2026-10-30T07:{60-minutes:02d}:00Z" if minutes <= 60 else "2026-10-30T06:00:00Z"}, "deploys": deploys}


class ReleaseLagTests(unittest.TestCase):
    def check(self, data, status):
        self.assertEqual(module.assess(data, now=NOW)["status"], status)

    def test_exact_full_sha_is_live(self):
        self.check(snapshot(live=MAIN), "LIVE")

    def test_exact_live_with_pending_ci_is_not_accepted(self):
        self.check(snapshot(live=MAIN, ci_status="in_progress"), "CI_PENDING")

    def test_exact_live_with_failed_ci_is_not_accepted(self):
        data = snapshot(live=MAIN)
        data["ci"]["jobs"][0]["conclusion"] = "failure"
        self.check(data, "CI_FAILED")

    def test_matching_prefix_is_not_live(self):
        self.check(snapshot(live=MAIN[:7] + OLD[7:]), "STALE_LIVE")

    def test_green_ci_stale_live(self):
        self.check(snapshot(), "STALE_LIVE")

    def test_recent_green_ci_pending(self):
        self.check(snapshot(minutes=10), "DEPLOY_PENDING")

    def test_ci_in_progress(self):
        self.check(snapshot(ci_status="in_progress"), "CI_PENDING")

    def test_ci_for_old_sha_is_not_current_evidence(self):
        self.check(snapshot(ci_sha=OLD), "CI_PENDING")

    def test_missing_required_job(self):
        data = snapshot()
        data["ci"]["jobs"].pop()
        self.check(data, "CI_PENDING")

    def test_failed_ci(self):
        data = snapshot()
        data["ci"]["jobs"][0]["conclusion"] = "failure"
        self.check(data, "CI_FAILED")

    def test_render_failed(self):
        self.check(snapshot(main_deploy="build_failed"), "DEPLOY_FAILED")

    def test_render_rolled_back(self):
        self.check(snapshot(main_deploy="deactivated"), "ROLLED_BACK")

    def test_render_building_recent(self):
        self.check(snapshot(minutes=10, main_deploy="build_in_progress"), "DEPLOY_PENDING")

    def test_render_building_too_long(self):
        self.check(snapshot(main_deploy="build_in_progress"), "STALE_LIVE")

    def test_two_conflicting_live_records_are_unverified(self):
        data = snapshot(live=MAIN)
        data["deploys"].append({"id": "conflicting-live", "status": "live", "commit": {"id": OLD}})
        result = module.assess(data, now=NOW)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertIn("multiple", result["reason"])

    def test_two_identical_live_records_are_still_unverified(self):
        data = snapshot(live=MAIN)
        data["deploys"].append({"id": "duplicate-live", "status": "live", "commit": {"id": MAIN}})
        self.check(data, "UNVERIFIED")

    def test_no_live_is_not_accepted(self):
        self.check(snapshot(status="deactivated"), "STALE_LIVE")

    def test_missing_timestamp_is_unverified(self):
        data = snapshot()
        data["ci"].pop("completed_at")
        self.check(data, "UNVERIFIED")

    def test_bad_sha_fails_closed(self):
        data = snapshot()
        data["main_sha"] = "a" * 7
        with self.assertRaises(ValueError):
            module.assess(data, now=NOW)

    def test_missing_snapshot_observation_is_unverified(self):
        data = snapshot(live=MAIN)
        data.pop("observed_at")
        self.check(data, "UNVERIFIED")

    def test_stale_snapshot_cannot_claim_old_main_live(self):
        data = snapshot(live=MAIN)
        data["observed_at"] = "2026-10-30T07:49:59Z"
        self.check(data, "UNVERIFIED")

    def test_future_observation_is_unverified(self):
        data = snapshot(live=MAIN)
        data["observed_at"] = "2026-10-30T08:02:00Z"
        self.check(data, "UNVERIFIED")

    def test_duplicate_required_ci_job_is_unverified(self):
        data = snapshot(live=MAIN)
        data["ci"]["jobs"].append(dict(data["ci"]["jobs"][0]))
        self.check(data, "UNVERIFIED")

    def test_ci_completion_after_snapshot_is_unverified(self):
        data = snapshot(live=MAIN)
        data["ci"]["completed_at"] = "2026-10-30T08:01:00Z"
        self.check(data, "UNVERIFIED")

    def test_naive_clock_fails_closed(self):
        with self.assertRaises(ValueError):
            module.assess(snapshot(), now=datetime(2026, 10, 30, 8, 0))


if __name__ == "__main__":
    unittest.main()
