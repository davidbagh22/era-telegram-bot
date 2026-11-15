"""Telegram webhook authentication and deployment diagnostics."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.webapp import _warn_if_webhook_secret_missing, app

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


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


class TelegramWebhookAuthenticationTests(TestCase):
    def test_incoming_webhook_requires_matching_secret(self) -> None:
        settings = Settings(bot_token="0000000000:CITESTTOKEN", webhook_secret="configured-test-secret")
        with patch.object(app.state, "settings", settings, create=True):
            client = TestClient(app)
            for headers in ([], [(SECRET_HEADER, "wrong-secret")], [(SECRET_HEADER.encode(), b"\xff")]):
                with self.subTest(headers=headers):
                    response = client.post("/telegram/webhook", headers=headers, content=b"invalid JSON")
                    self.assertEqual(response.status_code, 403)

    def test_missing_server_secret_fails_closed(self) -> None:
        settings = Settings(bot_token="0000000000:CITESTTOKEN", webhook_secret="")
        with patch.object(app.state, "settings", settings, create=True):
            client = TestClient(app)
            for headers in ({}, {SECRET_HEADER: "any-value"}):
                with self.subTest(headers=headers):
                    response = client.post("/telegram/webhook", headers=headers, content=b"invalid JSON")
                    self.assertEqual(response.status_code, 503)

    def test_matching_secret_dispatches_one_update(self) -> None:
        settings = Settings(bot_token="0000000000:CITESTTOKEN", webhook_secret="configured-test-secret")
        bot = object()
        dispatcher = SimpleNamespace(feed_update=AsyncMock())
        with patch.multiple(app.state, settings=settings, bot=bot, dispatcher=dispatcher, create=True):
            response = TestClient(app).post(
                "/telegram/webhook",
                headers={SECRET_HEADER: settings.effective_webhook_secret},
                json={"update_id": 123},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        dispatcher.feed_update.assert_awaited_once()
        called_bot, update = dispatcher.feed_update.await_args.args
        self.assertIs(called_bot, bot)
        self.assertEqual(update.update_id, 123)
