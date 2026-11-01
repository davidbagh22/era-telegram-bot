"""Fetch a read-only, exact-SHA release snapshot outside required GitHub checks.

Requires RENDER_API_KEY in the caller's environment. Never schedule this as a
checksPass-required workflow: a stale Render deploy must not block itself.
No deploys, settings changes, database queries or Telegram messages are made.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from render_release_lag import assess

REPO = "davidbagh22/era-telegram-bot"
SERVICE = "srv-d91r1j7avr4c73fs8h00"
GITHUB = f"https://api.github.com/repos/{REPO}"
RENDER = "https://api.render.com/v1"
_SHA = re.compile(r"^[0-9a-f]{40}$")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a Render API bearer token to a redirected destination.
        return None


def fetch_json(url: str, token: str | None = None, timeout: float = 10.0):
    if not (url.startswith(GITHUB + "/") or url.startswith(RENDER + "/")):
        raise ValueError("unapproved API origin")
    if url.startswith(RENDER + "/") and not token:
        raise ValueError("Render API key missing")
    headers = {"Accept": "application/json", "User-Agent": "ERA-readonly-release-monitor/1.0"}
    if token:
        if not url.startswith(RENDER + "/"):
            raise ValueError("bearer token must only be sent to Render")
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        return json.loads(response.read(2_000_000))


def _branch_sha(fetch) -> str:
    payload = fetch(GITHUB + "/branches/main")
    sha = payload.get("commit", {}).get("sha")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise ValueError("GitHub main SHA is unavailable or malformed")
    return sha


def collect(fetch, *, render_token: str, service_id: str = SERVICE) -> dict:
    """Read GitHub and Render once, then recheck main to reject mixed snapshots."""
    if not re.fullmatch(r"srv-[a-z0-9]+", service_id):
        raise ValueError("invalid Render service ID")
    main_sha = _branch_sha(fetch)
    runs = fetch(GITHUB + f"/actions/runs?head_sha={main_sha}&event=push&per_page=20")
    matches = [
        run for run in runs.get("workflow_runs", [])
        if run.get("head_sha") == main_sha
        and run.get("event") == "push"
        and run.get("name") == "Bot checks"
    ]
    matches.sort(key=lambda run: run.get("created_at") or "", reverse=True)
    ci = {"head_sha": main_sha, "jobs": []}
    if matches:
        run = matches[0]
        jobs_payload = fetch(GITHUB + f"/actions/runs/{int(run['id'])}/jobs?per_page=100")
        jobs = jobs_payload.get("jobs", [])
        if not isinstance(jobs, list):
            raise ValueError("GitHub CI jobs are malformed")
        ci["jobs"] = [
            {"name": job.get("name"), "status": job.get("status"),
             "conclusion": job.get("conclusion")} for job in jobs
        ]
        if run.get("status") == "completed" and run.get("conclusion") == "success":
            completed = [job.get("completed_at") for job in jobs]
            if jobs and all(isinstance(value, str) and value for value in completed):
                ci["completed_at"] = max(completed)
    raw = fetch(RENDER + f"/services/{service_id}/deploys?limit=20", render_token)
    if not isinstance(raw, list):
        raise ValueError("Render deploy list is malformed")
    deploys = []
    for entry in raw:
        item = entry.get("deploy", entry) if isinstance(entry, dict) else None
        if not isinstance(item, dict):
            raise ValueError("Render deploy entry is malformed")
        deploys.append({
            "id": item.get("id"),
            "status": item.get("status"),
            "commit": {"id": (item.get("commit") or {}).get("id")},
        })
    if _branch_sha(fetch) != main_sha:
        raise ValueError("main changed during read-only snapshot")
    return {
        "main_sha": main_sha,
        "ci": ci,
        "deploys": deploys,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-id", default=SERVICE)
    parser.add_argument("--max-lag-minutes", type=int, default=45)
    args = parser.parse_args()
    token = os.environ.get("RENDER_API_KEY")
    if not token:
        print(json.dumps({"status": "UNVERIFIED", "reason": "RENDER_API_KEY not configured"}))
        return 2
    try:
        snapshot = collect(fetch_json, render_token=token, service_id=args.service_id)
        result = assess(snapshot, now=datetime.now(timezone.utc),
                        max_lag_minutes=args.max_lag_minutes)
    except (ValueError, TypeError, KeyError, AttributeError, OSError,
            HTTPError, URLError, json.JSONDecodeError) as exc:
        # Do not echo exception text: upstream URLs or responses may be sensitive.
        print(json.dumps({"status": "UNVERIFIED", "reason": type(exc).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "LIVE" else (
        1 if result["status"] in {"STALE_LIVE", "DEPLOY_FAILED", "ROLLED_BACK", "CI_FAILED"}
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
