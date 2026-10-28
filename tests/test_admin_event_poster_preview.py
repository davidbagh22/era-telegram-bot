"""Draft poster previews must be private and usable by authorized event editors."""
from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
from fastapi.params import Depends

from app.api.v1.admin_event_create import read_admin_event_poster_preview, require_event_manager
from app.utils.constants import EventStatus


class AdminEventPosterPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def _preview(self, mime="image/png", status=EventStatus.DRAFT, data=b"poster"):
        session = SimpleNamespace(get=AsyncMock(side_effect=[
            SimpleNamespace(status=status) if status is not None else None,
            SimpleNamespace(poster_bytes=data, poster_content_type=mime),
        ]))
        return await read_admin_event_poster_preview(
            42, _admin=SimpleNamespace(id=7), session=session
        )

    async def test_draft_editor_preview_is_private_and_image_only(self):
        response = await self._preview()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"poster")
        self.assertEqual(response.media_type, "image/png")
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    async def test_unsafe_legacy_poster_mime_is_not_served(self):
        for mime in ("text/html", "image/svg+xml", "application/javascript"):
            with self.subTest(mime=mime), self.assertRaises(HTTPException) as caught:
                await self._preview(mime=mime)
            self.assertEqual(caught.exception.status_code, 404)

    async def test_missing_event_and_missing_poster_are_hidden(self):
        for kwargs in ({"status": None}, {"data": b""}):
            with self.subTest(kwargs=kwargs), self.assertRaises(HTTPException) as caught:
                await self._preview(**kwargs)
            self.assertEqual(caught.exception.status_code, 404)

    def test_editor_components_do_not_use_public_poster_urls(self):
        root = Path(__file__).resolve().parents[1]
        components = [
            root / "frontend/src/screens/admin/events/QuickEventCreateDialog.tsx",
            root / "frontend/src/screens/admin/events/AdminEventCreatePanel.tsx",
        ]
        for component in components:
            with self.subTest(component=component.name):
                source = component.read_text(encoding="utf-8")
                self.assertNotIn("/api/v1/event-posters/", source)
                self.assertIn("posterUrl", source)
        api = (root / "frontend/src/api/adminEvents.ts").read_text(encoding="utf-8")
        self.assertIn("Authorization: `Bearer ${sessionToken}`", api)
        self.assertIn("/poster/preview", api)

    def test_preview_route_requires_event_manager_dependency(self):
        dependency = inspect.signature(read_admin_event_poster_preview).parameters["_admin"].default
        self.assertIsInstance(dependency, Depends)
        self.assertIs(dependency.dependency, require_event_manager)


if __name__ == "__main__":
    unittest.main()
