"""Protect production smoke from a Render checksPass/workflow_run circular wait.

This only inspects repository workflow text. No HTTP, deployment or Telegram
operations are performed.
"""
from __future__ import annotations

from pathlib import Path
import unittest


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github" / "workflows" / "production-readonly-smoke.yml"
)


class ProductionSmokeWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_release_is_not_blocked_by_post_ci_smoke(self) -> None:
        text = self.workflow
        self.assertIn('  schedule:', text)
        self.assertIn('  workflow_dispatch:', text)
        self.assertNotIn('\n  workflow_run:', text)
        self.assertNotIn('\n  push:', text)
        self.assertIn('    - cron: "7,22,37,52 * * * *"', text)

    def test_read_only_smoke_checks_exact_checked_out_main(self) -> None:
        text = self.workflow
        self.assertIn('  contents: read', text)
        self.assertIn('persist-credentials: false', text)
        self.assertIn('          ref: main', text)
        self.assertIn('EXPECTED_SHA="$(git rev-parse HEAD)"', text)
        self.assertIn('production_readonly_smoke.py --expected-sha "$EXPECTED_SHA"', text)
        self.assertNotIn('actions/deploy', text)
        self.assertNotIn('trigger_deploy', text)


if __name__ == "__main__":
    unittest.main()
