"""Production acceptance probe must never send credentials or fake success."""
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts import production_readonly_smoke as smoke


class FakeResponse:
    def __init__(self, url, status, body=None):
        self.url = url
        self.status = status
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
            raise HTTPError(request.full_url, 401, "Unauthorized", None, None)

        with patch.object(smoke, "urlopen", side_effect=fake_open):
            status, checks = smoke.run()
        self.assertEqual(status, 0)
        self.assertEqual([item["status"] for item in checks[3:]], [401] * 4)

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
            body = json.dumps({"status": "ok", "commit": sha[:7]}).encode()
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
