"""Safe MIME and caching contract for the legacy public poster endpoint."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

from app.api.v1.event_posters import read_public_event_poster
from app.utils.constants import EventStatus


class PublicPosterMimeTests(unittest.IsolatedAsyncioTestCase):
    async def _response(
        self,
        content_type: str | None,
        poster_bytes: bytes = b"poster",
        status: EventStatus | None = EventStatus.PUBLISHED,
    ):
        session = SimpleNamespace(
            get=AsyncMock(
                side_effect=[
                    SimpleNamespace(status=status) if status is not None else None,
                    SimpleNamespace(
                        poster_bytes=poster_bytes,
                        poster_content_type=content_type,
                    ),
                ]
            )
        )
        return await read_public_event_poster(42, session=session)

    async def test_executable_and_unknown_mime_are_not_served(self) -> None:
        for content_type in (
            "text/html",
            "image/svg+xml",
            "application/javascript",
            "application/octet-stream",
            "text/html; charset=utf-8",
        ):
            with self.subTest(content_type=content_type):
                with self.assertRaises(HTTPException) as caught:
                    await self._response(content_type)
                self.assertEqual(caught.exception.status_code, 404)

    async def test_safe_mobile_images_and_legacy_jpeg_are_preserved(self) -> None:
        for content_type, expected in (
            (None, "image/jpeg"),
            (" IMAGE/PNG; charset=binary ", "image/png"),
            ("image/heic", "image/heic"),
            ("image/heif", "image/heif"),
            ("image/avif", "image/avif"),
            ("image/webp", "image/webp"),
        ):
            with self.subTest(content_type=content_type):
                response = await self._response(content_type)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.body, b"poster")
                self.assertEqual(response.media_type, expected)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    async def test_moderation_only_posters_and_unknown_events_are_hidden(self) -> None:
        for status in (EventStatus.DRAFT, EventStatus.PENDING_APPROVAL, None):
            with self.subTest(status=status):
                with self.assertRaises(HTTPException) as caught:
                    await self._response("image/png", status=status)
                self.assertEqual(caught.exception.status_code, 404)
                self.assertEqual(caught.exception.detail, "event_poster_not_found")

    async def test_cancelled_historical_links_remain_compatible(self) -> None:
        response = await self._response("image/jpeg", status=EventStatus.CANCELLED)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_missing_poster_remains_not_found(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            await self._response("image/jpeg", poster_bytes=b"")
        self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
