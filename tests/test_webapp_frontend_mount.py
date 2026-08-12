from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.webapp import _mount_frontend


class MountFrontendTests(unittest.TestCase):
    def test_missing_dist_directory_does_not_raise(self) -> None:
        app = FastAPI()
        missing_dir = Path(tempfile.gettempdir()) / "era-miniapp-dist-does-not-exist"
        _mount_frontend(app, missing_dir)
        # No route should have been mounted at /app.
        client = TestClient(app)
        response = client.get("/app/")
        self.assertEqual(response.status_code, 404)

    def test_existing_dist_directory_is_served(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist_dir = Path(tmp)
            (dist_dir / "index.html").write_text("<html>era</html>", encoding="utf-8")

            app = FastAPI()
            _mount_frontend(app, dist_dir)
            client = TestClient(app)
            response = client.get("/app/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("era", response.text)

    def test_index_html_is_never_cached(self) -> None:
        # Regression test: confirmed live on 2026-08-12 that a Telegram
        # Mini App WebView can go on rendering a stale build indefinitely
        # after a deploy, because plain StaticFiles sends no Cache-Control
        # at all and the WebView (unlike a normal browser) doesn't reliably
        # revalidate on its own. index.html — the one file whose reference
        # to the content-hashed asset filenames actually changes between
        # deploys — must always be revalidated.
        with tempfile.TemporaryDirectory() as tmp:
            dist_dir = Path(tmp)
            (dist_dir / "index.html").write_text("<html>era</html>", encoding="utf-8")

            app = FastAPI()
            _mount_frontend(app, dist_dir)
            client = TestClient(app)
            response = client.get("/app/")
            self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_hashed_assets_are_cached_forever(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist_dir = Path(tmp)
            (dist_dir / "index.html").write_text("<html>era</html>", encoding="utf-8")
            assets_dir = dist_dir / "assets"
            assets_dir.mkdir()
            (assets_dir / "index-abc123.js").write_text("console.log('era')", encoding="utf-8")

            app = FastAPI()
            _mount_frontend(app, dist_dir)
            client = TestClient(app)
            response = client.get("/app/assets/index-abc123.js")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "public, max-age=31536000, immutable")


if __name__ == "__main__":
    unittest.main()
