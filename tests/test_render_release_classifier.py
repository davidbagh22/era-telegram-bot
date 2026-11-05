"""Offline regression tests for Render release state classification."""
from datetime import datetime, timezone, timedelta
import pytest

from scripts.render_release_classifier import classify

MAIN = "a" * 40
OLD = "b" * 40
NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)
OK = ["success"] * 5


def deploy(sha, status, age=5):
    return {"commit": {"id": sha}, "status": status,
            "createdAt": (NOW - timedelta(minutes=age)).isoformat()}


def test_exact_live_requires_five_main_checks():
    assert classify(MAIN, [deploy(MAIN, "live")], OK, now=NOW)["state"] == "LIVE_EXACT"
    assert classify(MAIN, [deploy(MAIN, "live")], ["pending"] + OK[1:], now=NOW)["state"] == "UNVERIFIED"


@pytest.mark.parametrize(("age", "expected"), [(10, "DEPLOY_PENDING"), (46, "DEPLOY_STALE")])
def test_pending_and_stale(age, expected):
    result = classify(MAIN, [deploy(MAIN, "build_in_progress", age),
                             deploy(OLD, "live")], OK, now=NOW)
    assert result["state"] == expected
    assert result["live_sha"] == OLD


def test_failed_deploy_is_not_pending():
    assert classify(MAIN, [deploy(MAIN, "failed"), deploy(OLD, "live")],
                    OK, now=NOW)["state"] == "DEPLOY_FAILED"


def test_rollback_or_superseded_is_not_live():
    assert classify(MAIN, [deploy(MAIN, "deactivated"), deploy(OLD, "live")],
                    OK, now=NOW)["state"] == "ROLLBACK_OR_SUPERSEDED"


def test_no_exact_deploy_is_unverified_not_pending():
    assert classify(MAIN, [deploy(OLD, "live")], OK, now=NOW)["state"] == "UNVERIFIED"


def test_missing_or_multiple_live_is_unverified():
    assert classify(MAIN, [], OK, now=NOW)["state"] == "UNVERIFIED"
    assert classify(MAIN, [deploy(OLD, "live"), deploy(MAIN, "live")],
                    OK, now=NOW)["state"] == "UNVERIFIED"


def test_ci_failure_overrides_render():
    assert classify(MAIN, [deploy(MAIN, "live")], ["failed"] + OK[1:],
                    now=NOW)["state"] == "CI_FAILED"


def test_invalid_sha_and_timestamp_fail_closed():
    with pytest.raises(ValueError):
        classify("a" * 7, [], OK, now=NOW)
    assert classify(MAIN, [deploy(MAIN, "pending", -10), deploy(OLD, "live")],
                    OK, now=NOW)["state"] == "UNVERIFIED"


def test_unknown_render_status_is_unverified():
    assert classify(MAIN, [deploy(MAIN, "mystery"), deploy(OLD, "live")],
                    OK, now=NOW)["state"] == "UNVERIFIED"


def test_completed_workflow_status_is_not_success_conclusion():
    # GitHub Actions 'completed' is a run status, not a successful conclusion.
    result = classify(MAIN, [deploy(MAIN, "live")],
                      ["completed"] + OK[1:], now=NOW)
    assert result == {"state": "UNVERIFIED", "reason": "main_ci_incomplete_or_unknown"}
