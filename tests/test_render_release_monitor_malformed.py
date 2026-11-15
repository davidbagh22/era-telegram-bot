"""Malformed GitHub snapshots must not crash the independent monitor."""
import unittest
from unittest.mock import patch
from scripts import render_release_monitor as monitor


class MalformedChecksTests(unittest.TestCase):
    def test_malformed_check_collections_fail_closed(self):
        for checks in (None, [], {}, {"check_runs": None}, {"check_runs": {}},
                       {"check_runs": [None]}, {"check_runs": ["bad"]},
                       {"check_runs": [42]}):
            with self.subTest(checks=checks), patch.object(
                monitor, "get_json",
                side_effect=[{"commit": {"sha": "a" * 40}}, checks],
            ) as fetch:
                result = monitor.collect("fake", "fake")
                self.assertEqual(result, {
                    "state": "UNVERIFIED", "reason": "malformed_github_checks",
                })
                self.assertEqual(fetch.call_count, 2)

    def test_main_reports_malformed_checks_without_crashing(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "fake", "RENDER_API_KEY": "fake"}), patch.object(
            monitor, "get_json",
            side_effect=[{"commit": {"sha": "a" * 40}}, {"check_runs": [None]}],
        ), patch("builtins.print") as output:
            self.assertEqual(monitor.main(), 0)
            self.assertIn("malformed_github_checks", output.call_args.args[0])
