"""Classify exact GitHub main/CI versus Render LIVE from a read-only snapshot.

Offline classifier only: never attach this to checksPass-required GitHub checks.
It is NOT an external monitor, release acceptance, or Telegram device test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

REQUIRED_JOBS = frozenset({"test", "frontend", "secret-scan", "e2e", "postgres-migration"})
_SHA = re.compile(r"^[0-9a-f]{40}$")


def _timestamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return dt.astimezone(timezone.utc)


def assess(snapshot: dict, *, now: datetime, max_lag_minutes: int = 45) -> dict:
    """Classify exact SHA, completed required jobs, and Render LIVE only."""
    if now.tzinfo is None or max_lag_minutes < 1:
        raise ValueError("aware now and positive max_lag_minutes required")
    main = snapshot.get("main_sha")
    if not isinstance(main, str) or not _SHA.fullmatch(main):
        raise ValueError("main_sha must be an exact 40-character lowercase hex SHA")
    ci = snapshot.get("ci") or {}
    deploys = snapshot.get("deploys") or []
    if not isinstance(ci, dict) or not isinstance(deploys, list):
        raise ValueError("ci must be an object and deploys must be a list")

    live = next((d for d in deploys if d.get("status") == "live"), None)
    live_sha = (live or {}).get("commit", {}).get("id")
    latest_main = next((d for d in deploys if d.get("commit", {}).get("id") == main), None)
    result = {
        "main_sha": main,
        "live_sha": live_sha,
        "latest_main_deploy_id": (latest_main or {}).get("id"),
        "status": "UNVERIFIED",
        "reason": "insufficient evidence",
    }
    # A manually supplied snapshot is not current production evidence unless
    # its observation time is recent. Never accept an old main/LIVE pair.
    observed_raw = snapshot.get("observed_at")
    if not isinstance(observed_raw, str):
        result.update(status="UNVERIFIED", reason="snapshot observation timestamp missing")
        return result
    observed = _timestamp(observed_raw)
    observation_age = (now.astimezone(timezone.utc) - observed).total_seconds()
    if observation_age > 600 or observation_age < -60:
        result.update(status="UNVERIFIED", reason="snapshot observation timestamp is stale or in the future")
        return result
    if ci.get("head_sha") != main:
        result.update(status="CI_PENDING", reason="no CI evidence for exact main SHA")
        return result
    jobs = ci.get("jobs") or []
    if not isinstance(jobs, list):
        raise ValueError("ci.jobs must be a list")
    names = [j.get("name") for j in jobs if isinstance(j, dict)]
    if len(names) != len(jobs) or len(names) != len(set(names)):
        result.update(status="UNVERIFIED", reason="malformed or duplicate CI job records")
        return result
    by_name = {j["name"]: j for j in jobs}
    if not REQUIRED_JOBS.issubset(by_name):
        result.update(status="CI_PENDING", reason="required CI jobs missing")
        return result
    if any(by_name[name].get("conclusion") == "failure" for name in REQUIRED_JOBS):
        result.update(status="CI_FAILED", reason="required CI job failed")
        return result
    if any(by_name[name].get("status") != "completed" or by_name[name].get("conclusion") != "success" for name in REQUIRED_JOBS):
        result.update(status="CI_PENDING", reason="required CI jobs not all successful")
        return result
    if not ci.get("completed_at"):
        result.update(status="UNVERIFIED", reason="green CI completion timestamp missing")
        return result
    completed = _timestamp(ci["completed_at"])
    if completed > observed or completed > now.astimezone(timezone.utc):
        result.update(status="UNVERIFIED", reason="CI completion is later than snapshot observation")
        return result
    if live_sha == main and _SHA.fullmatch(live_sha):
        result.update(status="LIVE", reason="exact main SHA is Render LIVE with green CI")
        return result
    age_minutes = max(0, int((now.astimezone(timezone.utc) - completed).total_seconds() // 60))
    result["minutes_since_green_ci"] = age_minutes
    if latest_main and latest_main.get("status") in {"build_failed", "update_failed", "failed", "canceled"}:
        result.update(status="DEPLOY_FAILED", reason="exact-main Render deployment failed")
    elif latest_main and latest_main.get("status") == "deactivated":
        result.update(status="ROLLED_BACK", reason="exact-main deployment is no longer LIVE")
    elif age_minutes >= max_lag_minutes:
        result.update(status="STALE_LIVE", reason="CI green but exact main not LIVE within release SLO")
    else:
        result.update(status="DEPLOY_PENDING", reason="CI green; automatic Render deployment not yet LIVE")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="read-only JSON snapshot from GitHub and Render")
    parser.add_argument("--max-lag-minutes", type=int, default=45)
    parser.add_argument("--now", help="aware ISO8601 time for reproducible checks")
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        result = assess(snapshot, now=_timestamp(args.now) if args.now else datetime.now(timezone.utc), max_lag_minutes=args.max_lag_minutes)
    except (ValueError, OSError, json.JSONDecodeError, TypeError, AttributeError) as exc:
        print(json.dumps({"status": "UNVERIFIED", "reason": type(exc).__name__}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 1 if result["status"] in {"STALE_LIVE", "DEPLOY_FAILED", "ROLLED_BACK", "CI_FAILED"} else (0 if result["status"] == "LIVE" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
