"""Read-only production HTTP acceptance probe.

Never sends credentials or mutates server state. A DNS/transport failure is
UNVERIFIED (exit 2), never a successful security check.
"""
from __future__ import annotations

import argparse
import json
import re
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


def check(base_url: str, path: str, expected: frozenset[int], timeout: float, expected_sha: str | None = None) -> dict:
    url = base_url + path
    request = Request(
        url, method="GET",
        headers={"User-Agent": "ERA-readonly-smoke/1.0", "Cache-Control": "no-store"},
    )
    status: int | None = None
    final_url = url
    error: str | None = None
    health_commit: str | None = None
    content_type = ""
    auth_body: bytes | None = None
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            if path.startswith("/api/v1/") and status in expected:
                # A JSON Content-Type alone can be spoofed by a proxy. FastAPI
                # HTTPException responses carry a structured detail field.
                auth_body = response.read(4096)
            if path in ("/health", "/ready"):
                # A 200 HTML proxy/error page is not proof of a healthy app.
                # Verify the documented bounded JSON health/readiness body.
                try:
                    payload = json.loads(response.read(4096))
                    expected_status = "ok" if path == "/health" else "ready"
                    if not isinstance(payload, dict) or payload.get("status") != expected_status:
                        error = "health_payload_invalid" if path == "/health" else "ready_payload_invalid"
                    elif path == "/health" and expected_sha is not None:
                        health_commit = payload.get("commit")
                except (ValueError, UnicodeError):
                    error = "health_payload_unreadable" if path == "/health" else "ready_payload_unreadable"
            elif path == "/app/":
                # A generic 200 login/error page does not prove that the
                # Mini App frontend is served. Check the stable React mount.
                # Only inspect a bounded prefix; never persist page contents.
                html = response.read(65_536)
                if b'<div id="root"' not in html:
                    error = "miniapp_root_missing"
    except HTTPError as exc:
        status = exc.code
        final_url = exc.geturl()
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        try:
            if path.startswith("/api/v1/") and status in expected:
                auth_body = exc.read(4096) if getattr(exc, "fp", None) is not None else b""
        except (URLError, TimeoutError, OSError) as read_exc:
            status = None
            error = type(read_exc).__name__
        finally:
            exc.close()
    except (URLError, TimeoutError, OSError) as exc:
        # Even if headers arrived, a transport failure while reading /health
        # is not a verified response and must never be reported as PASS/FAIL.
        status = None
        error = type(exc).__name__

    # A proxy's HTML 401/403 page is not proof that the FastAPI route
    # itself enforced authentication. FastAPI auth errors use JSON.
    if path.startswith("/api/v1/") and status in expected and error is None:
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json" and not media_type.endswith("+json"):
            error = "auth_response_not_json"
        else:
            try:
                payload = json.loads(auth_body or b"")
            except (ValueError, UnicodeError):
                error = "auth_payload_unreadable"
            else:
                detail = payload.get("detail") if isinstance(payload, dict) else None
                if not isinstance(detail, (str, list)) or not detail:
                    error = "auth_payload_invalid"

    # Redirects must not change the HTTPS origin (including port). A 200
    # from an unrelated host or an HTTP downgrade proves nothing about ERA.
    final = urlsplit(final_url)
    original = urlsplit(base_url)
    same_origin = (
        final.scheme == original.scheme == "https"
        and final.hostname == original.hostname
        and (final.port or 443) == (original.port or 443)
    )
    # An auth route redirected to /login could return 401 there, creating a
    # false-positive for the ORIGINAL protected endpoint. Verify the exact
    # requested route, not merely a status on the same host.
    same_route = (
        final.path == urlsplit(url).path
        and not final.query
        and not final.fragment
    )
    if path == "/health" and expected_sha is not None and error is None:
        # /health intentionally exposes only RENDER_GIT_COMMIT[:7]. This is
        # corroborating evidence, NOT exact LIVE-SHA proof (use Render deploy).
        if health_commit != expected_sha[:7]:
            error = "health_commit_prefix_mismatch"
    return {
        "path": path,
        "status": status,
        "expected": sorted(expected),
        "ok": status in expected and same_origin and same_route and error is None,
        "error": error or ("cross_origin_redirect" if not same_origin else "redirected_route" if not same_route else None),
        "commit_prefix": health_commit if path == "/health" and expected_sha else None,
    }


def run(base_url: str = PRODUCTION_URL, timeout: float = 10.0,
        expected_sha: str | None = None) -> tuple[int, list[dict]]:
    origin = _validated_base_url(base_url)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if expected_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("expected SHA must be a full 40-character lowercase Git commit")
    results = [check(origin, path, expected, timeout, expected_sha) for path, expected in CHECKS]
    if any(item["status"] is None for item in results):
        return 2, results  # DNS/network error: UNVERIFIED
    return (0 if all(item["ok"] for item in results) else 1), results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=PRODUCTION_URL)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--expected-sha", help="full SHA; checks /health seven-character prefix only")
    args = parser.parse_args()
    try:
        exit_code, results = run(args.base_url, args.timeout, args.expected_sha)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"result": ("PASS" if exit_code == 0 else
                                  "UNVERIFIED" if exit_code == 2 else "FAIL"),
                      "checks": results}, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
