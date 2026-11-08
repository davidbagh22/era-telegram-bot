"""Deployment warning for an unauthenticated Telegram webhook.

This guard is observability-only: it must not alter set_webhook, secrets,
request handling, or live Telegram delivery.
"""
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.config import Settings

from app.webapp import app, _warn_if_webhook_secret_missing


class WebhookSecretStartupWarningTests(TestCase):
    def test_missing_secret_produces_actionable_warning(self) -> None:
        with patch("app.webapp.logger.warning") as warning:
            _warn_if_webhook_secret_missing("")
        warning.assert_called_once()
        message = warning.call_args.args[0]
        self.assertIn("WEBHOOK_SECRET", message)
        self.assertIn("cannot be authenticated", message)

    def test_configured_secret_does_not_warn(self) -> None:
        with patch("app.webapp.logger.warning") as warning:
            _warn_if_webhook_secret_missing("configured-secret-value")
        warning.assert_not_called()

    def test_warning_never_logs_secret_value(self) -> None:
        secret = "sensitive-value-never-log"
        with patch("app.webapp.logger.warning") as warning:
            _warn_if_webhook_secret_missing(secret)
            _warn_if_webhook_secret_missing("")
        self.assertEqual(warning.call_count, 1)
        self.assertNotIn(secret, str(warning.call_args))

    def test_incoming_webhook_requires_matching_secret(self) -> None:
        settings = Settings(bot_token="0000000000:CITESTTOKEN", webhook_secret="configured-test-secret")
        with patch.object(app.state, "settings", settings, create=True):
            client = TestClient(app)
            for headers in ({}, {"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"}):
                response = client.post("/telegram/webhook", headers=headers, json={})
                self.assertEqual(response.status_code, 403)

    def test_missing_server_secret_fails_closed(self) -> None:
        settings = Settings(bot_token="0000000000:CITESTTOKEN", webhook_secret="")
        with patch.object(app.state, "settings", settings, create=True):
            client = TestClient(app)
            response = client.post("/telegram/webhook",
                                   headers={"X-Telegram-Bot-Api-Secret-Token": "any-value"}, json={})
            self.assertEqual(response.status_code, 503)
