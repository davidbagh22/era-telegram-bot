from __future__ import annotations

import unittest

from app.handlers.admin.rights_block6 import _permissions_keyboard
from app.utils.constants import PERMISSION_LABELS, PERMISSIONS


class PermissionsKeyboardTests(unittest.TestCase):
    def test_builds_without_raising_undefined_name(self) -> None:
        # Regression test: PERMISSION_LABELS was used in this module without
        # being imported, so building this keyboard raised NameError at
        # runtime for every admin who opened a user's permissions screen.
        keyboard = _permissions_keyboard(1, active={next(iter(PERMISSIONS))})
        self.assertTrue(keyboard.inline_keyboard)

    def test_labels_are_rendered_not_raw_permission_keys(self) -> None:
        keyboard = _permissions_keyboard(1, active=set())
        texts = [row[0].text for row in keyboard.inline_keyboard[:-1]]
        for permission, label in PERMISSION_LABELS.items():
            matching = [text for text in texts if label in text]
            if permission in PERMISSIONS:
                self.assertTrue(matching, f"expected label for {permission!r} to render")


if __name__ == "__main__":
    unittest.main()
