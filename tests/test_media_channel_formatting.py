from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.database.media_models import MediaContentItem
from app.services.media_service import _send_content, format_media_channel_text


def _item(body: str, *, title: str | None = None) -> MediaContentItem:
    return MediaContentItem(
        source_kind="manual",
        source_key="test:format",
        kind="text",
        body=body,
        title=title,
        status="ready",
    )


def test_media_formatter_preserves_paragraphs_and_renders_bold() -> None:
    rendered = format_media_channel_text(
        _item("Первый абзац с **важным акцентом**.\n\nВторой абзац.")
    )
    assert rendered == "Первый абзац с <b>важным акцентом</b>.\n\nВторой абзац."


def test_media_formatter_escapes_untrusted_html() -> None:
    rendered = format_media_channel_text(_item("<script>alert('x')</script> **ок**"))
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<b>ок</b>" in rendered


def test_media_formatter_adds_real_title_as_heading_without_injecting_rubric() -> None:
    item = _item("Основной текст публикации.", title="Главная мысль")
    item.rubric = "Внутренняя рубрика"
    rendered = format_media_channel_text(item)
    assert rendered.startswith("<b>Главная мысль</b>\n\n")
    assert "Внутренняя рубрика" not in rendered


def test_long_wall_of_text_is_split_without_rewriting_words() -> None:
    sentence = "Это длинное предложение о работе сообщества и реальных проектах."
    body = " ".join(sentence for _ in range(12))
    rendered = format_media_channel_text(_item(body))
    assert "\n\n" in rendered
    assert rendered.replace("\n\n", " ") == body


@pytest.mark.asyncio
async def test_channel_sender_uses_html_parse_mode_only_for_media_post() -> None:
    calls: list[dict] = []

    class FakeBot:
        async def send_message(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(message_id=1)

    await _send_content(FakeBot(), -100123, _item("Текст с **жирным**."))
    assert calls == [
        {
            "chat_id": -100123,
            "text": "Текст с <b>жирным</b>.",
            "parse_mode": "HTML",
        }
    ]
