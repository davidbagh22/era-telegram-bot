"""Production acceptance probe must never send credentials or fake success."""
import unittest
from unittest.mock import patch
from urllib.error import URLError

from scripts import production_readonly_smoke as smoke


class FakeResponse:
    def __init__(self, url, status):
        self.url = url
        self.status = status

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

    def test_dns_failure_is_unverified_not_pass(self):
        with patch.object(smoke, "urlopen", side_effect=URLError("DNS unavailable")):
            status, checks = smoke.run()
        self.assertEqual(status, 2)
        self.assertTrue(all(item["status"] is None for item in checks))
        self.assertTrue(all(not item["ok"] for item in checks))

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

    def test_https_downgrade_redirect_is_not_accepted(self):
        with patch.object(smoke, "urlopen", return_value=FakeResponse(
            "http://era-telegram-bot.onrender.com/app/", 200
        )):
            result = smoke.check(smoke.PRODUCTION_URL, "/app/", frozenset({200}), 3.0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "cross_origin_redirect")

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
