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


if __name__ == "__main__":
    unittest.main()
