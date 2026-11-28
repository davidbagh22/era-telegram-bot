"""Independent scheduled Render LIVE lag monitor (outside checksPass).

Fetches exact GitHub main + Bot checks and Render LIVE via the existing
read-only snapshot collector, classifies with render_release_lag.assess, then
emits warning-only ops output. Never triggers deploys, never fails as a
required commit check (this script is for schedule/workflow_dispatch only).

Exit codes (advisory; do not attach to Render checksPass):
  0 — LIVE / pending / CI pending / healthy-enough to keep watching
  1 — STALE_LIVE / DEPLOY_FAILED / ROLLED_BACK / CI_FAILED (ops alert)
  2 — UNVERIFIED / collector error (missing evidence, not a release gate)
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from render_release_lag import assess  # noqa: E402
from render_release_snapshot import collect, fetch_json  # noqa: E402

ALERT_STATUSES = frozenset({"STALE_LIVE", "DEPLOY_FAILED", "ROLLED_BACK", "CI_FAILED"})


def _emit(result: dict) -> int:
    print(json.dumps(result, sort_keys=True))
    status = result.get("status")
    reason = result.get("reason") or ""
    if status in ALERT_STATUSES:
        print(
            f"::warning::Render LIVE monitor {status}: {reason} "
            f"main={result.get('main_sha')} live={result.get('live_sha')} "
            f"age_min={result.get('minutes_since_green_ci')}"
        )
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write(
                    f"### Render LIVE monitor: `{status}`\n\n"
                    f"- reason: {reason}\n"
                    f"- main: `{result.get('main_sha')}`\n"
                    f"- LIVE: `{result.get('live_sha')}`\n"
                    f"- minutes since green CI: `{result.get('minutes_since_green_ci')}`\n"
                    f"- latest main deploy: `{result.get('latest_main_deploy_id')}`\n"
                    "- This is an ops warning only; it must not gate Render checksPass.\n"
                )
        return 1
    if status == "LIVE":
        return 0
    if status in {"DEPLOY_PENDING", "CI_PENDING"}:
        print(f"::notice::Render LIVE monitor {status}: {reason}")
        return 0
    print(f"::warning::Render LIVE monitor UNVERIFIED: {reason}")
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-lag-minutes", type=int, default=45)
    parser.add_argument(
        "--warning-only",
        action="store_true",
        help="always exit 0 after annotations so the job cannot act as a gate",
    )
    args = parser.parse_args()
    token = os.environ.get("RENDER_API_KEY")
    if not token:
        result = {"status": "UNVERIFIED", "reason": "RENDER_API_KEY not configured"}
        code = _emit(result)
        return 0 if args.warning_only else code
    try:
        snapshot = collect(fetch_json, render_token=token)
        result = assess(
            snapshot,
            now=datetime.now(timezone.utc),
            max_lag_minutes=args.max_lag_minutes,
        )
    except Exception as exc:  # noqa: BLE001 — fail closed without leaking details
        result = {"status": "UNVERIFIED", "reason": type(exc).__name__}
        code = _emit(result)
        return 0 if args.warning_only else code
    code = _emit(result)
    return 0 if args.warning_only else code


if __name__ == "__main__":
    raise SystemExit(main())
