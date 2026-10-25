"""Regression tests for externally supplied media attachment URLs."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_session
from app.api.v1.media_extras import _manager, router


class MediaAttachmentUrlTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        def assign_id(item):
            item.id = 321

        self.session = SimpleNamespace(
            get=AsyncMock(return_value=object()),
            add=MagicMock(side_effect=assign_id),
            flush=AsyncMock(),
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[_manager] = lambda: SimpleNamespace(id=7)
        app.dependency_overrides[get_session] = lambda: self.session
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_invalid_links_are_rejected_before_any_database_access(self):
        invalid = (
            "javascript:alert(1)",
            "http://example.org/file",
            "https://user:password@example.org/file",
            "https://example.org:22/file",
            "https://example.org:abc/file",
            "https://example.org:99999/file",
            "https://[broken/file",
            "https://example.org\\@evil.example/file",
            "https://example.org/white space",
            "https://example.org/line\nbreak",
        )
        for url in invalid:
            with self.subTest(url=url):
                response = await self.client.post("/media/desk/attachments", json={
                    "target_type": "content",
                    "target_id": 1,
                    "media_type": "link",
                    "external_url": url,
                })
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["detail"], "Укажите HTTPS-ссылку на материал")
        self.session.get.assert_not_awaited()
        self.session.add.assert_not_called()

    async def test_valid_https_and_telegram_file_only_attachments_remain_supported(self):
        for values in (
            {"external_url": "https://example.org:443/guide"},
            {"telegram_file_id": "existing-telegram-file-id"},
        ):
            with self.subTest(values=values):
                response = await self.client.post("/media/desk/attachments", json={
                    "target_type": "content",
                    "target_id": 1,
                    "media_type": "link",
                    **values,
                })
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["id"], 321)
                self.assertEqual(response.json()["external_url"], values.get("external_url"))
        self.assertEqual(self.session.get.await_count, 2)
        self.assertEqual(self.session.add.call_count, 2)
        self.assertEqual(self.session.flush.await_count, 2)

    async def test_unsafe_link_is_not_accepted_even_with_telegram_file_id(self):
        response = await self.client.post("/media/desk/attachments", json={
            "target_type": "content",
            "target_id": 1,
            "media_type": "file",
            "external_url": "javascript:alert(1)",
            "telegram_file_id": "real-file-id",
        })
        self.assertEqual(response.status_code, 422, response.text)
        self.session.add.assert_not_called()
