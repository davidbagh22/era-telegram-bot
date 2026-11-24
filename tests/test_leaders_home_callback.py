"""Leaders native UI must use menu:main, not a dead home callback."""
from __future__ import annotations

import inspect
import unittest

from app.handlers import leaders_native


class LeadersHomeCallbackTests(unittest.TestCase):
    def test_main_menu_buttons_use_menu_main(self) -> None:
        source = inspect.getsource(leaders_native)
        self.assertIn("menu:main", source)
        self.assertNotIn("('← Главное меню','home')", source)
        self.assertNotIn("('Главная', 'home')", source)


if __name__ == "__main__":
    unittest.main()
