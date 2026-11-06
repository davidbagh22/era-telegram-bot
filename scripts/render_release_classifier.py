"""Pure read-only Render release classification for independent monitoring.

Inputs are externally obtained snapshots. This module never calls Render,
GitHub, Telegram, or production. A missing/ambiguous fact is UNVERIFIED.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

SHA = re.compile(r"^[0-9a-f]{40}$")
SUCCESS = {"success"}
FAILURE = {"failed", "build_failed", "update_failed", "canceled", "cancelled"}


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def classify(main_sha: str, deploys: list[dict], ci_checks: list[str],
             *, now: datetime, grace_minutes: int = 45) -> dict:
    """Classify exact-SHA release status without treating health prefix as proof.

    deploys: newest-first Render deploy snapshots, each with status,
    commit.id, createdAt. A LIVE deployment must have full commit SHA.
    ci_checks: the five required main push check conclusions.
    """
    if not isinstance(main_sha, str) or not SHA.fullmatch(main_sha):
        raise ValueError("main_sha must be full lowercase SHA")
    if not isinstance(now, datetime) or now.tzinfo is None or not isinstance(grace_minutes, (int, float)) or grace_minutes < 0:
        raise ValueError("aware now and nonnegative grace required")
    if not isinstance(ci_checks, list) or len(ci_checks) != 5 or any(
        not isinstance(c, str) or c not in SUCCESS | FAILURE | {"pending", "in_progress", "queued"}
        for c in ci_checks
    ):
        return {"state": "UNVERIFIED", "reason": "main_ci_incomplete_or_unknown"}
    if any(c in FAILURE for c in ci_checks):
        return {"state": "CI_FAILED", "reason": "main_ci_failed"}
    if not isinstance(deploys, list) or not deploys:
        return {"state": "UNVERIFIED", "reason": "render_deploys_missing"}
    if any(not isinstance(d, dict) or not isinstance(d.get("commit"), dict) for d in deploys):
        return {"state": "UNVERIFIED", "reason": "malformed_render_snapshot"}
    live = [d for d in deploys if d.get("status") == "live"]
    if len(live) != 1:
        return {"state": "UNVERIFIED", "reason": "unique_live_deploy_not_confirmed"}
    live_sha = (live[0].get("commit") or {}).get("id")
    if not isinstance(live_sha, str) or not SHA.fullmatch(live_sha):
        return {"state": "UNVERIFIED", "reason": "live_sha_missing"}
    if live_sha == main_sha:
        if all(c in SUCCESS for c in ci_checks):
            return {"state": "LIVE_EXACT", "live_sha": live_sha}
        return {"state": "UNVERIFIED", "reason": "main_ci_pending", "live_sha": live_sha}
    candidates = [d for d in deploys if (d.get("commit") or {}).get("id") == main_sha]
    if not candidates:
        return {"state": "UNVERIFIED", "reason": "main_deploy_not_in_snapshot", "live_sha": live_sha}
    latest = candidates[0]
    status = latest.get("status")
    if status in FAILURE:
        return {"state": "DEPLOY_FAILED", "live_sha": live_sha}
    if status in {"deactivated", "superseded"}:
        return {"state": "ROLLBACK_OR_SUPERSEDED", "live_sha": live_sha}
    if not isinstance(status, str) or status not in {"created", "build_in_progress", "update_in_progress", "pending", "build_succeeded"}:
        return {"state": "UNVERIFIED", "reason": "unknown_deploy_status", "live_sha": live_sha}
    try:
        created = _time(latest["createdAt"])
        age = (now.astimezone(timezone.utc) - created).total_seconds() / 60
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError):
        return {"state": "UNVERIFIED", "reason": "invalid_deploy_timestamp", "live_sha": live_sha}
    if age < 0:
        return {"state": "UNVERIFIED", "reason": "future_deploy_timestamp", "live_sha": live_sha}
    if not all(c in SUCCESS for c in ci_checks):
        return {"state": "CI_PENDING", "live_sha": live_sha}
    return {"state": "DEPLOY_STALE" if age > grace_minutes else "DEPLOY_PENDING",
            "age_minutes": round(age, 1), "live_sha": live_sha}
