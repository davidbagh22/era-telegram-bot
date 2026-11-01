"""No-network tests for the optional read-only release snapshot collector."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import render_release_snapshot as module  # noqa: E402
from render_release_lag import REQUIRED_JOBS, assess  # noqa: E402

MAIN = "a" * 40
OLD = "b" * 40


class FakeAPI:
    def __init__(self, *, live=MAIN, ci="success", change_main=False, malformed=False):
        self.live = live
        self.ci = ci
        self.change_main = change_main
        self.malformed = malformed
        self.branch_reads = 0
        self.urls = []
        self.completed_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()

    def __call__(self, url, token=None):
        self.urls.append(url)
        if url.endswith("/branches/main"):
            self.branch_reads += 1
            return {"commit": {"sha": OLD if self.change_main and self.branch_reads > 1 else MAIN}}
        if "/actions/runs?" in url:
            return {"workflow_runs": [{
                "id": 123, "name": "Bot checks", "event": "push",
                "head_sha": MAIN,
                "created_at": self.completed_at,
                "status": "completed" if self.ci == "success" else "in_progress",
                "conclusion": "success" if self.ci == "success" else None,
            }]}
        if "/actions/runs/123/jobs?" in url:
            return {"jobs": [{
                "name": name,
                "status": "completed" if self.ci == "success" else "in_progress",
                "conclusion": "success" if self.ci == "success" else None,
                "completed_at": self.completed_at if self.ci == "success" else None,
            } for name in sorted(REQUIRED_JOBS)]}
        if "/deploys?" in url:
            self.assert_token(token)
            if self.malformed:
                return {"deploys": []}
            return [{"deploy": {
                "id": "dep-test", "status": "live", "commit": {"id": self.live},
            }}]
        raise AssertionError(f"Unexpected URL: {url}")

    @staticmethod
    def assert_token(token):
        if token != "fixture-only":
            raise AssertionError("Render-only test token missing")


class SnapshotCollectorTests(unittest.TestCase):
    def test_exact_live_with_five_successful_jobs(self):
        api = FakeAPI()
        snapshot = module.collect(api, render_token="fixture-only")
        self.assertEqual(snapshot["main_sha"], MAIN)
        self.assertEqual(len(snapshot["ci"]["jobs"]), 5)
        self.assertEqual(api.branch_reads, 2)
        self.assertEqual(assess(snapshot, now=datetime.now(timezone.utc))["status"], "LIVE")

    def test_green_ci_with_stale_live_is_not_accepted(self):
        snapshot = module.collect(FakeAPI(live=OLD), render_token="fixture-only")
        self.assertEqual(assess(snapshot, now=datetime.now(timezone.utc))["status"], "DEPLOY_PENDING")

    def test_pending_ci_with_matching_live_is_not_accepted(self):
        snapshot = module.collect(FakeAPI(ci="pending"), render_token="fixture-only")
        self.assertEqual(assess(snapshot, now=datetime.now(timezone.utc))["status"], "CI_PENDING")

    def test_main_race_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "main changed"):
            module.collect(FakeAPI(change_main=True), render_token="fixture-only")

    def test_malformed_render_payload_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "deploy list"):
            module.collect(FakeAPI(malformed=True), render_token="fixture-only")

    def test_reject_invalid_service_id_before_requests(self):
        api = FakeAPI()
        with self.assertRaisesRegex(ValueError, "service ID"):
            module.collect(api, render_token="fixture-only", service_id="../../secrets")
        self.assertEqual(api.urls, [])

    def test_unmatched_ci_run_is_pending(self):
        class MissingCI(FakeAPI):
            def __call__(self, url, token=None):
                if "/actions/runs?" in url:
                    return {"workflow_runs": []}
                return super().__call__(url, token)
        snapshot = module.collect(MissingCI(), render_token="fixture-only")
        self.assertEqual(assess(snapshot, now=datetime.now(timezone.utc))["status"], "CI_PENDING")


if __name__ == "__main__":
    unittest.main()
