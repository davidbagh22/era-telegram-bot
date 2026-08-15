from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlsplit

from app.config import Settings

BOT_TOKEN = "1234567890:test-token"


class EffectiveMiniAppUrlTests(unittest.TestCase):
    def test_falls_back_to_base_url_slash_app(self) -> None:
        settings = Settings(
            bot_token=BOT_TOKEN,
            public_base_url="https://era.onrender.com",
            miniapp_auth_secret="s3cr3t",
        )
        self.assertEqual(settings.effective_miniapp_url, "https://era.onrender.com/app/")

    def test_explicit_miniapp_url_overrides_base_url(self) -> None:
        settings = Settings(
            bot_token=BOT_TOKEN,
            public_base_url="https://era.onrender.com",
            miniapp_url="https://custom-host.example/",
            miniapp_auth_secret="s3cr3t",
        )
        self.assertEqual(settings.effective_miniapp_url, "https://custom-host.example")

    def test_empty_when_no_base_url_configured(self) -> None:
        settings = Settings(bot_token=BOT_TOKEN, miniapp_auth_secret="s3cr3t")
        self.assertEqual(settings.effective_miniapp_url, "")

    def test_uses_render_external_hostname_when_public_base_url_unset(self) -> None:
        settings = Settings(
            bot_token=BOT_TOKEN,
            render_external_hostname="era-telegram-bot.onrender.com",
            miniapp_auth_secret="s3cr3t",
        )
        self.assertEqual(
            settings.effective_miniapp_url,
            "https://era-telegram-bot.onrender.com/app/",
        )

    def test_hidden_when_auth_secret_is_not_configured(self) -> None:
        settings = Settings(
            bot_token=BOT_TOKEN,
            public_base_url="https://era.onrender.com",
            miniapp_url="https://custom-host.example/",
        )
        self.assertEqual(settings.effective_miniapp_url, "")

    def test_render_release_sha_busts_telegram_webview_cache(self) -> None:
        settings = Settings(
            bot_token=BOT_TOKEN,
            render_external_hostname="era-telegram-bot.onrender.com",
            render_git_commit="5b57c9a15ffd52d0c2eb45b285ce9ecefb6fa566",
            miniapp_auth_secret="s3cr3t",
        )
        parsed = urlsplit(settings.effective_miniapp_url)
        self.assertEqual(parsed.path, "/app/")
        self.assertEqual(parse_qs(parsed.query), {"v": ["5b57c9a15ffd"]})

    def test_release_cache_buster_preserves_existing_query_parameters(self) -> None:
        settings = Settings(
            bot_token=BOT_TOKEN,
            miniapp_url="https://custom-host.example/app/?tenant=era",
            render_git_commit="abcdef1234567890",
            miniapp_auth_secret="s3cr3t",
        )
        parsed = urlsplit(settings.effective_miniapp_url)
        self.assertEqual(parse_qs(parsed.query), {"tenant": ["era"], "v": ["abcdef123456"]})


if __name__ == "__main__":
    unittest.main()
