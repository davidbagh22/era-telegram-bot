"""Read-only production HTTP acceptance probe.

Never sends credentials or mutates server state. A DNS/transport failure is
UNVERIFIED (exit 2), never a successful security check.
"""
from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

PRODUCTION_URL = "https://era-telegram-bot.onrender.com"
CHECKS: tuple[tuple[str, frozenset[int]], ...] = (
    ("/health", frozenset({200})),
    ("/ready", frozenset({200})),
    ("/app/", frozenset({200})),
    ("/api/v1/admin/analytics/v2", frozenset({401, 403})),
    ("/api/v1/admin/analytics/executive-report.pdf", frozenset({401, 403})),
    ("/api/v1/admin/analytics/executive-report.xlsx", frozenset({401, 403})),
    ("/api/v1/media/workspaces", frozenset({401, 403})),
)


def _validated_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base URL must be an HTTPS origin without credentials or path")
    return base_url.rstrip("/")


def check(base_url: str, path: str, expected: frozenset[int], timeout: float) -> dict:
    url = base_url + path
    request = Request(
        url, method="GET",
        headers={"User-Agent": "ERA-readonly-smoke/1.0", "Cache-Control": "no-store"},
    )
    status: int | None = None
    final_url = url
    error: str | None = None
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            final_url = response.geturl()
    except HTTPError as exc:
        status = exc.code
        final_url = exc.geturl()
        exc.close()
    except (URLError, TimeoutError, OSError) as exc:
        error = type(exc).__name__

    # Never treat an unrelated host reached via redirect as acceptance.
    same_host = urlsplit(final_url).hostname == urlsplit(base_url).hostname
    return {
        "path": path,
        "status": status,
        "expected": sorted(expected),
        "ok": status in expected and same_host,
        "error": error or ("cross_host_redirect" if not same_host else None),
    }


def run(base_url: str = PRODUCTION_URL, timeout: float = 10.0) -> tuple[int, list[dict]]:
    origin = _validated_base_url(base_url)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    results = [check(origin, path, expected, timeout) for path, expected in CHECKS]
    if any(item["status"] is None for item in results):
        return 2, results  # DNS/network error: UNVERIFIED
    return (0 if all(item["ok"] for item in results) else 1), results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=PRODUCTION_URL)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    try:
        exit_code, results = run(args.base_url, args.timeout)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"result": ("PASS" if exit_code == 0 else
                                  "UNVERIFIED" if exit_code == 2 else "FAIL"),
                      "checks": results}, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
