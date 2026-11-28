"""Independent Render LIVE lag monitor and optional ops alert (#565).

Compares exact GitHub main tip + completed Bot checks against the process LIVE
SHA (RENDER_GIT_COMMIT). Classification reuses scripts/render_release_lag.assess
so pending / failed / rolled-back / stale / healthy stay consistent with the
offline collector.

This path is intentionally outside Render checksPass-required GitHub checks.
Admin Telegram DMs stay OFF unless feature_render_live_stale_alerts is enabled;
when enabled, delivery uses durable safe_send_once keys only (no mass broadcast).
"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import logging
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

REPO = "davidbagh22/era-telegram-bot"
GITHUB = f"https://api.github.com/repos/{REPO}"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(bot[_-]?token|token|secret|password|api[_-]?key)\s*[=:]\s*[^\s,;]+"
    ),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
)
ALERT_STATUSES = frozenset({"STALE_LIVE", "DEPLOY_FAILED", "ROLLED_BACK"})
MAX_LAG_MINUTES = 45


def current_commit_sha() -> str | None:
    """Exact process LIVE SHA from Render/Git env (not the public /health[:7])."""
    value = (
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GITHUB_SHA")
        or os.getenv("ERA_COMMIT_SHA")
        or ""
    ).strip()
    return value[:64] or None


def _sanitize(value: object, *, limit: int = 700) -> str:
    text_value = str(value or "").replace("\x00", " ")
    for pattern in _SECRET_PATTERNS:
        text_value = pattern.sub("[REDACTED]", text_value)
    text_value = re.sub(r"https?://[^\s]+", "[URL_REDACTED]", text_value)
    text_value = " ".join(text_value.split())
    return text_value[:limit]


@lru_cache(maxsize=1)
def _lag_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "render_release_lag.py"
    spec = importlib.util.spec_from_file_location("render_release_lag", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("render_release_lag unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def should_alert(status: str | None) -> bool:
    """True only for SLO breach / failed deploy / rollback — never for pending CI."""
    return str(status or "") in ALERT_STATUSES


def format_ops_alert(result: dict[str, Any]) -> str:
    """Human ops text with SHAs and age; never includes tokens or URLs with secrets."""
    status = str(result.get("status") or "UNVERIFIED")
    reason = _sanitize(result.get("reason") or "insufficient evidence")
    main_sha = str(result.get("main_sha") or "unknown")
    live_sha = str(result.get("live_sha") or "unknown")
    age = result.get("minutes_since_green_ci")
    age_line = f"Minutes since green CI: {age}\n" if isinstance(age, int) else ""
    deploy_id = result.get("latest_main_deploy_id")
    deploy_line = f"Latest main deploy id: {deploy_id}\n" if deploy_id else ""
    return (
        "⚠️ ЭРА: Render LIVE отстаёт от main\n\n"
        f"Статус: {status}\n"
        f"Причина: {reason}\n"
        f"main: {main_sha}\n"
        f"LIVE: {live_sha}\n"
        f"{age_line}"
        f"{deploy_line}"
        f"SLO: {MAX_LAG_MINUTES} мин после зелёного CI\n"
        "Это ops-предупреждение, не checksPass и не production acceptance."
    )


def durable_alert_key(result: dict[str, Any]) -> str:
    """Stable per-episode key so retries do not spam admins for the same lag."""
    status = str(result.get("status") or "unknown")
    main_sha = str(result.get("main_sha") or "none")[:40]
    live_sha = str(result.get("live_sha") or "none")[:40]
    return f"render-live-stale:{status}:{main_sha}:{live_sha}"


def _github_get(url: str, *, timeout: float = 10.0) -> Any:
    if not url.startswith(GITHUB + "/"):
        raise ValueError("unapproved GitHub origin")
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ERA-render-live-monitor/1.0",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(2_000_000))


def build_live_process_snapshot(
    fetch: Callable[[str], Any],
    *,
    live_sha: str,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Read-only GitHub main/CI + this process LIVE SHA (exact, not /health[:7])."""
    if not isinstance(live_sha, str) or not _SHA.fullmatch(live_sha):
        raise ValueError("live_sha must be an exact 40-character lowercase hex SHA")
    branch = fetch(GITHUB + "/branches/main")
    main_sha = (branch.get("commit") or {}).get("sha")
    if not isinstance(main_sha, str) or not _SHA.fullmatch(main_sha):
        raise ValueError("GitHub main SHA is unavailable or malformed")

    runs_payload = fetch(
        GITHUB + f"/actions/runs?head_sha={main_sha}&event=push&per_page=20"
    )
    if not isinstance(runs_payload, dict) or not isinstance(
        runs_payload.get("workflow_runs"), list
    ):
        raise ValueError("GitHub workflow runs are malformed")
    matches = [
        run
        for run in runs_payload["workflow_runs"]
        if isinstance(run, dict)
        and run.get("head_sha") == main_sha
        and run.get("event") == "push"
        and run.get("name") == "Bot checks"
    ]
    matches.sort(key=lambda run: run.get("created_at") or "", reverse=True)
    ci: dict[str, Any] = {"head_sha": main_sha, "jobs": []}
    if matches:
        run = matches[0]
        ci["workflow_status"] = run.get("status")
        ci["workflow_conclusion"] = run.get("conclusion")
        jobs_payload = fetch(GITHUB + f"/actions/runs/{int(run['id'])}/jobs?per_page=100")
        if not isinstance(jobs_payload, dict):
            raise ValueError("GitHub CI jobs response is malformed")
        jobs = jobs_payload.get("jobs")
        if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
            raise ValueError("GitHub CI jobs are malformed")
        ci["jobs"] = [
            {
                "name": job.get("name"),
                "status": job.get("status"),
                "conclusion": job.get("conclusion"),
            }
            for job in jobs
        ]
        if run.get("status") == "completed" and run.get("conclusion") == "success":
            completed = [job.get("completed_at") for job in jobs]
            if jobs and all(isinstance(value, str) and value for value in completed):
                ci["completed_at"] = max(completed)

    # Recheck main so a concurrent push cannot mix evidence.
    branch_again = fetch(GITHUB + "/branches/main")
    main_again = (branch_again.get("commit") or {}).get("sha")
    if main_again != main_sha:
        raise ValueError("main changed during read-only snapshot")

    observed = observed_at or datetime.now(timezone.utc)
    return {
        "main_sha": main_sha,
        "ci": ci,
        "deploys": [
            {
                "id": "process-live",
                "status": "live",
                "commit": {"id": live_sha},
            }
        ],
        "observed_at": observed.astimezone(timezone.utc).isoformat(),
    }


def classify_snapshot(
    snapshot: dict[str, Any],
    *,
    now: datetime | None = None,
    max_lag_minutes: int = MAX_LAG_MINUTES,
) -> dict[str, Any]:
    return _lag_module().assess(
        snapshot,
        now=now or datetime.now(timezone.utc),
        max_lag_minutes=max_lag_minutes,
    )


def alerts_enabled(settings: Settings) -> bool:
    return getattr(settings, "feature_render_live_stale_alerts", "OFF") != "OFF"


async def maybe_notify_stale_live(
    bot: "Bot",
    settings: Settings,
    result: dict[str, Any],
    *,
    notify_once: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Send durable admin DM only when enabled and status warrants an alert."""
    outcome = {
        "alerted": False,
        "skipped_reason": None,
        "sent": 0,
        "failed": 0,
        "duplicates": 0,
    }
    if not should_alert(result.get("status")):
        outcome["skipped_reason"] = "status_not_alertable"
        return outcome
    if not alerts_enabled(settings):
        outcome["skipped_reason"] = "feature_disabled"
        return outcome
    if notify_once is None:
        from app.services.notification_service import notify_admins_once as notify_once
    text = format_ops_alert(result)
    sent, failed, duplicates = await notify_once(
        bot,
        settings,
        text,
        delivery_key=durable_alert_key(result),
        notification_type="render_live_stale",
    )
    outcome.update(
        alerted=True,
        sent=sent,
        failed=failed,
        duplicates=duplicates,
    )
    return outcome


async def run_render_live_monitor(
    bot: "Bot",
    settings: Settings,
    session_factory=None,  # noqa: ARG001 — scheduler signature parity
    *,
    fetch: Callable[[str], Any] | None = None,
    now: datetime | None = None,
    snapshot_builder: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Scheduler entry: classify LIVE vs main and optionally notify admins."""
    live_sha = current_commit_sha()
    payload: dict[str, Any] = {
        "status": "UNVERIFIED",
        "reason": "insufficient evidence",
        "live_sha": live_sha,
    }
    if not settings.is_render_deployment:
        payload["reason"] = "not_render_deployment"
        return payload
    if not isinstance(live_sha, str) or not _SHA.fullmatch(live_sha):
        payload["reason"] = "process_live_sha_unavailable"
        logger.warning("Render LIVE monitor skipped: process SHA unavailable")
        return payload
    try:
        builder = snapshot_builder or build_live_process_snapshot
        if inspect.iscoroutinefunction(builder):
            snapshot = await builder(
                fetch or _github_get, live_sha=live_sha, observed_at=now
            )
        else:
            # urllib is blocking: never run it on the scheduler/webhook event loop.
            snapshot = await asyncio.to_thread(
                builder, fetch or _github_get, live_sha=live_sha, observed_at=now
            )
        result = classify_snapshot(snapshot, now=now)
    except (ValueError, TypeError, KeyError, AttributeError, OSError, HTTPError, URLError, json.JSONDecodeError) as exc:
        # Never echo exception text — upstream payloads may be sensitive.
        logger.warning("Render LIVE monitor unverified: %s", type(exc).__name__)
        payload["reason"] = type(exc).__name__
        return payload

    notify = await maybe_notify_stale_live(bot, settings, result)
    logger.info(
        "Render LIVE monitor status=%s alerted=%s skipped=%s",
        result.get("status"),
        notify.get("alerted"),
        notify.get("skipped_reason"),
    )
    return {**result, "notify": notify}
