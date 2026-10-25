from __future__ import annotations

import unittest

from app.api.v1.media_rich_publish import _RichMediaBot
from app.utils.telegram_html import sanitize_telegram_html


class TelegramHTMLTests(unittest.TestCase):
    def test_supported_formatting_is_preserved_and_canonicalized(self) -> None:
        value = sanitize_telegram_html(
            '<strong>Важно</strong> <em>сейчас</em>\n<blockquote>Цитата</blockquote>'
        )
        self.assertEqual(
            value,
            '<b>Важно</b> <i>сейчас</i>\n<blockquote>Цитата</blockquote>',
        )

    def test_unsafe_markup_and_links_cannot_reach_telegram(self) -> None:
        value = sanitize_telegram_html(
            '<script>alert(1)</script><a href="javascript:alert(1)" onclick="x">ссылка</a>'
        )
        self.assertEqual(value, 'alert(1)ссылка')
        self.assertNotIn('javascript:', value)
        self.assertNotIn('onclick', value)
        self.assertNotIn('<script', value)

    def test_plain_angle_brackets_are_escaped(self) -> None:
        value = sanitize_telegram_html('Рост 2 < 3 & развитие > отчёта')
        self.assertIn('&lt;', value)
        self.assertIn('&amp;', value)
        self.assertIn('&gt;', value)


class _FakeBot:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        return object()


class RichMediaBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_media_proxy_sets_html_and_sanitizes_body(self) -> None:
        bot = _FakeBot()
        proxy = _RichMediaBot(bot)  # type: ignore[arg-type]

        await proxy.send_message(
            chat_id='@era_leaders1',
            text='<b>Заголовок</b>\n\n<a href="https://example.com">Подробнее</a>',
        )

        self.assertEqual(len(bot.calls), 1)
        call = bot.calls[0]
        self.assertEqual(call['parse_mode'], 'HTML')
        self.assertEqual(
            call['text'],
            '<b>Заголовок</b>\n\n<a href="https://example.com">Подробнее</a>',
        )


if __name__ == '__main__':
    unittest.main()
