from __future__ import annotations

import unittest

from app.config import Settings


class DeploymentSafetyTests(unittest.TestCase):
    def test_dev_auth_on_render_refuses_to_start(self) -> None:
        settings = Settings(
            bot_token="1234567890:test-token",
            dev_auth_enabled=True,
            render_external_hostname="era-telegram-bot.onrender.com",
        )
        with self.assertRaises(RuntimeError):
            settings.assert_safe_for_deployment()

    def test_dev_auth_locally_is_fine(self) -> None:
        settings = Settings(
            bot_token="1234567890:test-token",
            dev_auth_enabled=True,
            render_external_hostname="",
        )
        settings.assert_safe_for_deployment()  # must not raise

    def test_dev_auth_disabled_on_render_is_fine(self) -> None:
        settings = Settings(
            bot_token="1234567890:test-token",
            dev_auth_enabled=False,
            render_external_hostname="era-telegram-bot.onrender.com",
        )
        settings.assert_safe_for_deployment()  # must not raise

    def test_init_data_max_age_default_is_one_hour(self) -> None:
        settings = Settings(bot_token="1234567890:test-token")
        self.assertEqual(settings.init_data_max_age_seconds, 3600)


if __name__ == "__main__":
    unittest.main()
