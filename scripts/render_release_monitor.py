"""Independent read-only release snapshot collector; never a required push check.

Requires GITHUB_TOKEN and RENDER_API_KEY supplied by the monitoring environment.
Missing credentials or ambiguous CI results fail closed as UNVERIFIED.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from scripts.render_release_classifier import classify

REPO = "davidbagh22/era-telegram-bot"
SERVICE = "srv-d91r1j7avr4c73fs8h00"


def get_json(url: str, token: str, *, github: bool = False) -> object:
    headers = {"Accept": "application/vnd.github+json" if github else "application/json",
               "Authorization": ("Bearer " if github else "Bearer ") + token,
               "User-Agent": "era-independent-release-monitor"}
    with urlopen(Request(url, headers=headers), timeout=12) as response:
        return json.load(response)


def collect(github_token: str, render_token: str) -> dict:
    base = "https://api.github.com/repos/" + REPO
    branch = get_json(base + "/branches/main", github_token, github=True)
    main_sha = branch["commit"]["sha"]
    checks = get_json(base + "/commits/" + main_sha + "/check-runs?per_page=100",
                      github_token, github=True)
    runs = checks["check_runs"]
    # Never infer success from an arbitrary subset of check runs. Names must
    # be explicitly configured to match the five required main checks.
    names = [x.strip() for x in os.getenv("ERA_MAIN_CHECK_NAMES", "").split(",") if x.strip()]
    if len(names) != 5 or len(set(names)) != 5:
        conclusions = []
    else:
        conclusions = []
        for name in names:
            matches = [r for r in runs if r.get("name") == name and
                       r.get("head_sha") == main_sha]
            conclusions.append(matches[0].get("conclusion") or "pending"
                               if len(matches) == 1 else "unknown")
    deployments = get_json("https://api.render.com/v1/services/" + SERVICE +
                           "/deploys?limit=20", render_token)
    # Render's API returns envelopes containing a deploy object.
    if isinstance(deployments, list):
        deployments = [item.get("deploy", item) if isinstance(item, dict) else item
                       for item in deployments]
    return classify(main_sha, deployments, conclusions, now=datetime.now(timezone.utc))


def main() -> int:
    github_token = os.getenv("GITHUB_TOKEN")
    render_token = os.getenv("RENDER_API_KEY")
    if not github_token or not render_token:
        result = {"state": "UNVERIFIED", "reason": "monitor_credentials_missing"}
    else:
        try:
            result = collect(github_token, render_token)
        except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError, IndexError):
            result = {"state": "UNVERIFIED", "reason": "snapshot_fetch_failed"}
    print(json.dumps(result, sort_keys=True))
    # This monitor is observational, not a required checksPass gate.
    return 0


if __name__ == "__main__":
    sys.exit(main())
