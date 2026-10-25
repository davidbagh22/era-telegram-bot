from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DockerignoreAllowsFrontendSourceTests(unittest.TestCase):
    """Regression test: the Dockerfile COPYs frontend/ to build the Mini App
    (see Dockerfile's `miniapp-build` stage). A blanket `frontend` entry in
    .dockerignore excludes the whole directory from the build context and
    breaks that COPY with "not found" — this happened once already."""

    def test_dockerignore_does_not_blanket_exclude_frontend(self) -> None:
        lines = {
            line.strip()
            for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        }
        self.assertNotIn("frontend", lines)
        self.assertNotIn("frontend/", lines)
        self.assertNotIn("/frontend", lines)

    def test_dockerfile_still_copies_frontend_for_the_build_stage(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY frontend/", dockerfile)


if __name__ == "__main__":
    unittest.main()
