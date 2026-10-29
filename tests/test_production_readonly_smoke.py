"""Production acceptance probe must never send credentials or fake success."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts import production_readonly_smoke as smoke


class FakeResponse:
    def __init__(self, url, status, body=None):
        self.url = url
        self.status = status
        self.headers = {"Content-Type": "application/json" if status in (401, 403) or url.endswith(("/health", "/ready")) else "text/html"}
        if body is None:
            if url.endswith("/app/"):
                body = b'<!doctype html><html><body><div id="root"></div></body></html>'
            elif url.endswith("/health"):
                body = b'{"status":"ok","commit":"unknown"}'
            elif url.endswith("/ready"):
                body = b'{"status":"ready"}'
            elif status in (401, 403):
                body = b'{"detail":"Not authenticated"}'
        self.body = body or b""

    def read(self, size):
        return self.body[:size]

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ProductionReadonlySmokeTests(unittest.TestCase):
    def test_expected_statuses_pass_without_authentication(self):
        requests = []

        def fake_open(request, timeout):
            self.assertEqual(request.get_method(), "GET")
            self.assertIsNone(request.get_header("Authorization"))
            self.assertEqual(timeout, 3.0)
            requests.append(request.full_url)
            code = 200 if request.full_url.endswith(("/health", "/ready", "/app/")) else 401
            return FakeResponse(request.full_url, code)

        with patch.object(smoke, "urlopen", side_effect=fake_open):
            status, checks = smoke.run(timeout=3.0)
        self.assertEqual(status, 0)
        self.assertEqual(len(requests), len(smoke.CHECKS))
        self.assertTrue(all(item["ok"] for item in checks))

    def test_real_urllib_401_exception_is_accepted_for_protected_routes(self):
        def fake_open(request, timeout):
            if request.full_url.endswith(("/health", "/ready", "/app/")):
                return FakeResponse(request.full_url, 200)
            raise HTTPError(request.full_url, 401, "Unauthorized", {"Content-Type": "application/json"}, io.BytesIO(b'{"detail":"Not authenticated"}'))

        with patch.object(smoke, "urlopen", side_effect=fake_open):
            status, checks = smoke.run()
        self.assertEqual(status, 0)
        self.assertEqual([item["status"] for item in checks[3:]], [401] * (len(smoke.CHECKS) - 3))

    def test_proxy_html_401_does_not_count_as_api_authorization(self):
        path = "/api/v1/media/workspaces"
        url = smoke.PRODUCTION_URL + path
        with patch.object(smoke, "urlopen", side_effect=HTTPError(
            url, 401, "Unauthorized", {"Content-Type": "text/html; charset=utf-8"}, None
        )):
            result = smoke.check(smoke.PRODUCTION_URL, path, frozenset({401, 403}), 3.0)
        self.assertEqual(result["status"], 401)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "auth_response_not_json")

    def test_fastapi_json_403_counts_as_authorization(self):
        path = "/api/v1/media/workspaces"
        url = smoke.PRODUCTION_URL + path
        with patch.object(smoke, "urlopen", side_effect=HTTPError(
            url, 403, "Forbidden", {"Content-Type": "application/json; charset=utf-8"}, io.BytesIO(b'{"detail":"Forbidden"}')
        )):
            result = smoke.check(smoke.PRODUCTION_URL, path, frozenset({401, 403}), 3.0)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["error"])

    def test_proxy_json_without_fastapi_detail_does_not_count_as_authorization(self):
        path = "/api/v1/media/workspaces"
        url = smoke.PRODUCTION_URL + path
        for body, expected_error in (
            (b"{}", "auth_payload_invalid"),
            (b'{"message":"login required"}', "auth_payload_invalid"),
            (b"<html>bad gateway</html>", "auth_payload_unreadable"),
            (b"", "auth_payload_unreadable"),
        ):
            with self.subTest(body=body), patch.object(smoke, "urlopen", side_effect=HTTPError(
                url, 401, "Unauthorized", {"Content-Type": "application/json"}, io.BytesIO(body)
            )):
                result = smoke.check(smoke.PRODUCTION_URL, path, frozenset({401, 403}), 3.0)
            self.assertEqual(result["status"], 401)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], expected_error)

    def test_dns_failure_is_unverified_not_pass(self):
        with patch.object(smoke, "urlopen", side_effect=URLError("DNS unavailable")):
            status, checks = smoke.run()
        self.assertEqual(status, 2)
        self.assertTrue(all(item["status"] is None for item in checks))
        self.assertTrue(all(not item["ok"] for item in checks))

    def test_health_body_transport_failure_is_unverified(self):
        class BrokenHealth(FakeResponse):
            def read(self, size):
                raise OSError("connection closed during body")

        def fake_open(request, timeout):
            if request.full_url.endswith("/health"):
                return BrokenHealth(request.full_url, 200)
            code = 200 if request.full_url.endswith(("/ready", "/app/")) else 401
            return FakeResponse(request.full_url, code)

        with patch.object(smoke, "urlopen", side_effect=fake_open):
            status, checks = smoke.run(expected_sha="a" * 40)
        self.assertEqual(status, 2)
        self.assertIsNone(checks[0]["status"])
        self.assertEqual(checks[0]["error"], "OSError")

    def test_generic_200_pages_are_not_health_or_readiness(self):
        for path, error in (
            ("/health", "health_payload_unreadable"),
            ("/ready", "ready_payload_unreadable"),
        ):
            with self.subTest(path=path), patch.object(
                smoke, "urlopen", return_value=FakeResponse(
                    smoke.PRODUCTION_URL + path, 200,
                    body=b"<html><body>Service unavailable</body></html>",
                ),
            ):
                result = smoke.check(
                    smoke.PRODUCTION_URL, path, frozenset({200}), 3.0
                )
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], error)

    def test_health_ready_json_payload_with_html_content_type_is_not_accepted(self):
        for path, body, expected_error in (
            ("/health", b'{"status":"ok"}', "health_response_not_json"),
            ("/ready", b'{"status":"ready"}', "ready_response_not_json"),
        ):
            with self.subTest(path=path):
                response = FakeResponse(smoke.PRODUCTION_URL + path, 200, body=body)
                response.headers["Content-Type"] = "text/html; charset=utf-8"
                with patch.object(smoke, "urlopen", return_value=response):
                    result = smoke.check(smoke.PRODUCTION_URL, path, frozenset({200}), 3.0)
                self.assertEqual(result["status"], 200)
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], expected_error)

    def test_json_200_with_wrong_status_is_not_ready(self):
        with patch.object(smoke, "urlopen", return_value=FakeResponse(
            smoke.PRODUCTION_URL + "/ready", 200,
            body=b'{"status":"starting"}',
        )):
            result = smoke.check(
                smoke.PRODUCTION_URL, "/ready", frozenset({200}), 3.0
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "ready_payload_invalid")

    def test_generic_200_login_page_is_not_miniapp_acceptance(self):
        # A same-origin login/error page with HTTP 200 is not the React app.
        with patch.object(smoke, "urlopen", return_value=FakeResponse(
            smoke.PRODUCTION_URL + "/app/", 200,
            body=b"<html><body>Sign in to continue</body></html>",
        )):
            result = smoke.check(
                smoke.PRODUCTION_URL, "/app/", frozenset({200}), 3.0
            )
        self.assertEqual(result["status"], 200)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "miniapp_root_missing")

    def test_non_html_miniapp_response_cannot_fake_react_mount(self):
        # A proxy's JSON/plaintext payload containing the expected root
        # marker is not evidence that the Mini App HTML is being served.
        for content_type in ("application/json", "text/plain", "application/octet-stream"):
            with self.subTest(content_type=content_type):
                response = FakeResponse(
                    smoke.PRODUCTION_URL + "/app/", 200,
                    body=b'<div id="root"></div>',
                )
                response.headers["Content-Type"] = content_type
                with patch.object(smoke, "urlopen", return_value=response):
                    result = smoke.check(
                        smoke.PRODUCTION_URL, "/app/", frozenset({200}), 3.0
                    )
                self.assertEqual(result["status"], 200)
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], "miniapp_response_not_html")

    def test_miniapp_root_must_be_a_real_div_element(self):
        # A matching byte string in JS, an HTML comment, an attribute prefix,
        # or another tag must not make the read-only acceptance probe pass.
        invalid_pages = (
            b'<html><script>const template = \'<div id="root"></div>\';</script></html>',
            b'<!-- <div id="root"></div> -->',
            b'<div id="rooted"></div>',
            b'<span id="root"></span>',
            b'<template><div id="root"></div></template>',
            b'<noscript><div id="root"></div></noscript>',
            b'<div id="root"',
        )
        for html in invalid_pages:
            with self.subTest(html=html):
                response = FakeResponse(smoke.PRODUCTION_URL + "/app/", 200, body=html)
                with patch.object(smoke, "urlopen", return_value=response):
                    result = smoke.check(
                        smoke.PRODUCTION_URL, "/app/", frozenset({200}), 3.0
                    )
                self.assertEqual(result["status"], 200)
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], "miniapp_root_missing")

    def test_miniapp_root_accepts_valid_html_attribute_variants(self):
        for html in (
            b"<html><body><div class='app' id='root'></div></body></html>",
            b'<html><div id = "root" data-version="1"></div></html>',
        ):
            with self.subTest(html=html):
                response = FakeResponse(smoke.PRODUCTION_URL + "/app/", 200, body=html)
                with patch.object(smoke, "urlopen", return_value=response):
                    result = smoke.check(
                        smoke.PRODUCTION_URL, "/app/", frozenset({200}), 3.0
                    )
                self.assertTrue(result["ok"])

    def test_html_charset_miniapp_response_is_accepted(self):
        response = FakeResponse(smoke.PRODUCTION_URL + "/app/", 200)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        with patch.object(smoke, "urlopen", return_value=response):
            result = smoke.check(
                smoke.PRODUCTION_URL, "/app/", frozenset({200}), 3.0
            )
        self.assertTrue(result["ok"])

    def test_miniapp_html_read_failure_is_unverified(self):
        class BrokenApp(FakeResponse):
            def read(self, size):
                raise OSError("connection closed during Mini App response")

        with patch.object(smoke, "urlopen", return_value=BrokenApp(
            smoke.PRODUCTION_URL + "/app/", 200
        )):
            result = smoke.check(
                smoke.PRODUCTION_URL, "/app/", frozenset({200}), 3.0
            )
        self.assertIsNone(result["status"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "OSError")

    def test_unprotected_analytics_endpoint_fails(self):
        def fake_open(request, timeout):
            return FakeResponse(request.full_url, 200)

        with patch.object(smoke, "urlopen", side_effect=fake_open):
            status, checks = smoke.run()
        self.assertEqual(status, 1)
        self.assertTrue(all(item["ok"] for item in checks[:3]))
        self.assertTrue(all(not item["ok"] for item in checks[3:]))

    def test_cross_host_redirect_is_not_accepted(self):
        with patch.object(smoke, "urlopen", return_value=FakeResponse(
            "https://unrelated.example/app/", 200
        )):
            result = smoke.check(smoke.PRODUCTION_URL, "/app/", frozenset({200}), 3.0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "cross_origin_redirect")

    def test_same_origin_login_redirect_cannot_fake_protected_route(self):
        # A 401 from /login is not proof that /media/workspaces enforces auth.
        with patch.object(smoke, "urlopen", return_value=FakeResponse(
            smoke.PRODUCTION_URL + "/login", 401
        )):
            result = smoke.check(
                smoke.PRODUCTION_URL, "/api/v1/media/workspaces",
                frozenset({401, 403}), 3.0,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "redirected_route")

    def test_https_downgrade_redirect_is_not_accepted(self):
        with patch.object(smoke, "urlopen", return_value=FakeResponse(
            "http://era-telegram-bot.onrender.com/app/", 200
        )):
            result = smoke.check(smoke.PRODUCTION_URL, "/app/", frozenset({200}), 3.0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "cross_origin_redirect")

    def test_health_commit_prefix_is_corroboration_not_exact_sha_proof(self):
        sha = "a88dca9220b246727553b266b0a36786464bfc25"

        def fake_open(request, timeout):
            body = (
                json.dumps({"status": "ok", "commit": sha[:7]}).encode()
                if request.full_url.endswith("/health")
                else None
            )
            return FakeResponse(
                request.full_url,
                200 if request.full_url.endswith(("/health", "/ready", "/app/")) else 401,
                body,
            )

        with patch.object(smoke, "urlopen", side_effect=fake_open):
            status, checks = smoke.run(expected_sha=sha)
        self.assertEqual(status, 0)
        self.assertEqual(checks[0]["commit_prefix"], sha[:7])
        with patch.object(smoke, "urlopen", side_effect=fake_open):
            status, checks = smoke.run(expected_sha="f" * 40)
        self.assertEqual(status, 1)
        self.assertEqual(checks[0]["error"], "health_commit_prefix_mismatch")
        with self.assertRaises(ValueError):
            smoke.run(expected_sha="a88dca9")

    def test_reject_non_https_or_embedded_credentials(self):
        for origin in (
            "http://era-telegram-bot.onrender.com",
            "https://user:pass@era-telegram-bot.onrender.com",
            "https://era-telegram-bot.onrender.com/private",
            "https://era-telegram-bot.onrender.com/?token=secret",
        ):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                smoke.run(origin)


if __name__ == "__main__":
    unittest.main()
