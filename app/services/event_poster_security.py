"""Fail-closed MIME validation shared by public and authenticated event posters."""

SAFE_EVENT_POSTER_MIME_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/avif",
        "image/heic",
        "image/heif",
    }
)


def normalized_event_poster_mime(raw_content_type: str | None) -> str | None:
    """Return a browser-safe image MIME, or None for executable/unknown content.

    Keep legacy posters with missing MIME as JPEG; the response layer adds
    X-Content-Type-Options: nosniff to prevent browser content sniffing.
    """
    normalized = (raw_content_type or "image/jpeg").split(";", 1)[0].strip().lower()
    return normalized if normalized in SAFE_EVENT_POSTER_MIME_TYPES else None
