"""Offline collector tests: no external requests or production mutations."""
from unittest.mock import patch

from scripts import render_release_monitor as monitor

MAIN = "a" * 40
OLD = "b" * 40


def fake_api(url, token, *, github=False):
    if url.endswith("/branches/main"):
        return {"commit": {"sha": MAIN}}
    if "/check-runs?" in url:
        return {"check_runs": [
            {"name": f"gate-{n}", "head_sha": MAIN, "conclusion": "success"}
            for n in range(5)
        ]}
    if "/deploys?" in url:
        return [{"deploy": {"commit": {"id": MAIN}, "status": "live"}}]
    raise AssertionError("unexpected endpoint")


def test_exact_release_with_five_explicit_checks(monkeypatch):
    monkeypatch.setenv("ERA_MAIN_CHECK_NAMES", ",".join(f"gate-{n}" for n in range(5)))
    with patch.object(monitor, "get_json", side_effect=fake_api):
        assert monitor.collect("fake-github", "fake-render")["state"] == "LIVE_EXACT"


def test_missing_check_names_fail_closed(monkeypatch):
    monkeypatch.delenv("ERA_MAIN_CHECK_NAMES", raising=False)
    with patch.object(monitor, "get_json", side_effect=fake_api):
        assert monitor.collect("fake-github", "fake-render")["state"] == "UNVERIFIED"


def test_wrong_check_sha_fails_closed(monkeypatch):
    monkeypatch.setenv("ERA_MAIN_CHECK_NAMES", ",".join(f"gate-{n}" for n in range(5)))
    def wrong_sha(url, token, *, github=False):
        result = fake_api(url, token, github=github)
        if "/check-runs?" in url:
            result["check_runs"][0]["head_sha"] = OLD
        return result
    with patch.object(monitor, "get_json", side_effect=wrong_sha):
        assert monitor.collect("fake-github", "fake-render")["state"] == "UNVERIFIED"


def test_no_credentials_never_fetches(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("RENDER_API_KEY", raising=False)
    with patch.object(monitor, "get_json", side_effect=AssertionError("network called")):
        assert monitor.main() == 0
    assert "monitor_credentials_missing" in capsys.readouterr().out



def test_render_api_envelope_and_failed_deploy(monkeypatch):
    monkeypatch.setenv("ERA_MAIN_CHECK_NAMES", ",".join(f"gate-{n}" for n in range(5)))
    def failed_deploy(url, token, *, github=False):
        result = fake_api(url, token, github=github)
        if "/deploys?" in url:
            return [
                {"deploy": {"commit": {"id": MAIN}, "status": "build_failed"}},
                {"deploy": {"commit": {"id": OLD}, "status": "live"}},
            ]
        return result
    with patch.object(monitor, "get_json", side_effect=failed_deploy):
        assert monitor.collect("fake-github", "fake-render")["state"] == "DEPLOY_FAILED"


def test_ambiguous_duplicate_check_fails_closed(monkeypatch):
    monkeypatch.setenv("ERA_MAIN_CHECK_NAMES", ",".join(f"gate-{n}" for n in range(5)))
    def duplicated(url, token, *, github=False):
        result = fake_api(url, token, github=github)
        if "/check-runs?" in url:
            result["check_runs"].append(dict(result["check_runs"][0]))
        return result
    with patch.object(monitor, "get_json", side_effect=duplicated):
        assert monitor.collect("fake-github", "fake-render")["state"] == "UNVERIFIED"


def test_unexpected_render_schema_fails_closed(monkeypatch):
    monkeypatch.setenv("ERA_MAIN_CHECK_NAMES", ",".join(f"gate-{n}" for n in range(5)))
    def malformed(url, token, *, github=False):
        if "/deploys?" in url:
            return {"unexpected": "schema"}
        return fake_api(url, token, github=github)
    with patch.object(monitor, "get_json", side_effect=malformed):
        assert monitor.collect("fake-github", "fake-render")["state"] == "UNVERIFIED"
