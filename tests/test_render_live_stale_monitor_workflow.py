"""Contract: Render LIVE stale monitor must never gate checksPass."""
from __future__ import annotations

from pathlib import Path
import unittest


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "render-live-stale-monitor.yml"
)
SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "render_live_stale_monitor.py"
)


class RenderLiveStaleMonitorWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_schedule_only_never_push_or_workflow_run(self):
        text = self.workflow
        self.assertIn("  schedule:", text)
        self.assertIn("  workflow_dispatch:", text)
        self.assertNotIn("\n  workflow_run:", text)
        self.assertNotIn("\n  push:", text)
        self.assertIn('    - cron: "12,42 * * * *"', text)

    def test_warning_only_and_no_deploy_actions(self):
        text = self.workflow
        self.assertIn("--warning-only", text)
        self.assertIn("render_live_stale_monitor.py", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("          ref: main", text)
        self.assertNotIn("actions/deploy", text)
        self.assertNotIn("trigger_deploy", text)

    def test_script_documents_advisory_exit_and_alert_statuses(self):
        self.assertIn("--warning-only", self.script)
        self.assertIn("STALE_LIVE", self.script)
        self.assertIn("DEPLOY_FAILED", self.script)
        self.assertIn("ROLLED_BACK", self.script)
        self.assertIn("checksPass", self.script)


if __name__ == "__main__":
    unittest.main()
