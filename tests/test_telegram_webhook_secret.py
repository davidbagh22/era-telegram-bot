"""Public Telegram webhook must fail closed when polling mode has no secret."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import BackgroundTasks, HTTPException

from app.webapp import telegram_webhook


class TelegramWebhookSecretTests(IsolatedAsyncioTestCase):
    def request(self, expected_secret: str):
        bot = object()
        dispatcher = SimpleNamespace(feed_update=AsyncMock())
        state = SimpleNamespace(
            settings=SimpleNamespace(effective_webhook_secret=expected_secret),
            bot=bot,
            dispatcher=dispatcher,
        )
        return SimpleNamespace(
            app=SimpleNamespace(state=state),
            json=AsyncMock(return_value={"update_id": 123}),
        )

    async def test_unconfigured_webhook_rejects_anonymous_forged_update(self) -> None:
        for supplied in (None, "", "attacker-value"):
            with self.subTest(supplied=supplied):
                request = self.request("")
                tasks = BackgroundTasks()
                with self.assertRaises(HTTPException) as error:
                    await telegram_webhook(request, tasks, secret=supplied)
                self.assertEqual(error.exception.status_code, 403)
                request.json.assert_not_awaited()
                self.assertEqual(tasks.tasks, [])

    async def test_configured_webhook_rejects_missing_or_wrong_secret(self) -> None:
        for supplied in (None, "", "incorrect"):
            with self.subTest(supplied=supplied):
                request = self.request("expected-secret")
                tasks = BackgroundTasks()
                with self.assertRaises(HTTPException) as error:
                    await telegram_webhook(request, tasks, secret=supplied)
                self.assertEqual(error.exception.status_code, 403)
                request.json.assert_not_awaited()
                self.assertEqual(tasks.tasks, [])

    async def test_configured_matching_secret_queues_one_update(self) -> None:
        request = self.request("expected-secret")
        tasks = BackgroundTasks()
        update = object()
        with patch("app.webapp.Update.model_validate", return_value=update) as validate:
            result = await telegram_webhook(
                request, tasks, secret="expected-secret"
            )
        self.assertEqual(result, {"ok": True})
        request.json.assert_awaited_once_with()
        validate.assert_called_once_with(
            {"update_id": 123}, context={"bot": request.app.state.bot}
        )
        self.assertEqual(len(tasks.tasks), 1)
        self.assertIs(tasks.tasks[0].func, request.app.state.dispatcher.feed_update)
        self.assertEqual(tasks.tasks[0].args, (request.app.state.bot, update))
