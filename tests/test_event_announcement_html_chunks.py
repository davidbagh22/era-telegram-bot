"""Read-only Telegram announcement HTML/UTF-16 chunking regressions.

These tests use only pure functions. They never publish a message, register a
participant, change points, or connect to production services.
"""
from html import unescape
import re

import pytest

from app.services.event_publication_service import escaped_text_parts


@pytest.mark.parametrize(
    ("text", "first_limit"),
    [
        ("🎉&<>\n" * 850 + "Конец", 1000),  # poster caption followed by text
        ("x" * 999 + "&" + "🎉" * 2000 + "<", 1000),  # entity at caption edge
        ("А" * 4000 + "&" + "Б" * 4000, 4000),  # text-only announcement
        ("<b>Тест</b> & " * 500, 1000),  # literal markup must stay escaped
    ],
)
def test_announcement_html_chunks_preserve_text_and_telegram_utf16_limits(text, first_limit):
    chunks = escaped_text_parts(text, first_limit=first_limit)

    assert chunks
    assert all(chunks), "Nonempty announcements must not produce empty Telegram messages"
    assert len(chunks[0].encode("utf-16-le")) // 2 <= first_limit
    assert all(len(chunk.encode("utf-16-le")) // 2 <= 4000 for chunk in chunks[1:])
    assert unescape("".join(chunks)) == text

    for chunk in chunks:
        assert "<" not in chunk and ">" not in chunk, "Raw markup must not be injected"
        assert re.search(r"&(?!amp;|lt;|gt;)", chunk) is None, (
            "HTML entities must not be split across Telegram messages"
        )
