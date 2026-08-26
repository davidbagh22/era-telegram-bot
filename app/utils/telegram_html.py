from __future__ import annotations

from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

_ALLOWED_TAGS = {
    "b": "b",
    "strong": "b",
    "i": "i",
    "em": "i",
    "u": "u",
    "s": "s",
    "strike": "s",
    "del": "s",
    "code": "code",
    "pre": "pre",
    "blockquote": "blockquote",
    "a": "a",
}
_ALLOWED_LINK_SCHEMES = {"http", "https", "tg"}


def _safe_href(value: str) -> str | None:
    href = unescape(value).strip()
    if not href:
        return None
    parsed = urlparse(href)
    if parsed.scheme.lower() not in _ALLOWED_LINK_SCHEMES:
        return None
    return href


class _TelegramHTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.stack: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        source = tag.lower()
        canonical = _ALLOWED_TAGS.get(source)
        if canonical is None:
            return

        if canonical == "a":
            href = next((value for name, value in attrs if name.lower() == "href" and value), None)
            safe_href = _safe_href(href or "")
            if safe_href is None:
                self.stack.append((source, None))
                return
            self.parts.append(f'<a href="{escape(safe_href, quote=True)}">')
            self.stack.append((source, "a"))
            return

        self.parts.append(f"<{canonical}>")
        self.stack.append((source, canonical))

    def handle_endtag(self, tag: str) -> None:
        source = tag.lower()
        match_index = next(
            (index for index in range(len(self.stack) - 1, -1, -1) if self.stack[index][0] == source),
            None,
        )
        if match_index is None:
            return
        while len(self.stack) > match_index:
            _source, canonical = self.stack.pop()
            if canonical:
                self.parts.append(f"</{canonical}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        self.parts.append(escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        self.parts.append(escape(unescape(f"&{name};"), quote=False))

    def handle_charref(self, name: str) -> None:
        self.parts.append(escape(unescape(f"&#{name};"), quote=False))

    def finish(self) -> str:
        while self.stack:
            _source, canonical = self.stack.pop()
            if canonical:
                self.parts.append(f"</{canonical}>")
        return "".join(self.parts)


def sanitize_telegram_html(value: str) -> str:
    """Return safe Telegram HTML while preserving normal text and line breaks.

    Media editors can use the small subset Telegram supports. Unsupported tags
    are removed while their text survives; link attributes are limited to a
    validated href so stored content cannot inject arbitrary markup.
    """
    parser = _TelegramHTMLSanitizer()
    parser.feed(value)
    parser.close()
    return parser.finish()
