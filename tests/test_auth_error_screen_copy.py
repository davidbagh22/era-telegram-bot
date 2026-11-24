"""Auth error screen must not expose raw English API detail strings."""
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]


class AuthErrorScreenCopyTests(TestCase):
    def test_support_footer_uses_russian_labels_not_raw_detail(self) -> None:
        source = (ROOT / "frontend/src/screens/AuthErrorScreen.tsx").read_text(encoding="utf-8")
        self.assertIn("Код для поддержки:", source)
        self.assertIn("нет данных входа", source)
        self.assertIn("нет регистрации", source)
        self.assertNotIn("Код: {code} · {detail}", source)
