from __future__ import annotations

import re
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.handlers.admin.literature_editor import router

ROOT = Path(__file__).resolve().parents[1]


class StaticCallbackAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = runpy.run_path(str(ROOT / "scripts" / "system_audit_report.py"))

    def test_complete_audit_has_no_unexplained_failed_checks(self):
        self.assertEqual(self.audit["report"]["issues"], [])

    def test_editorial_regex_covers_buttons_without_accepting_an_orphan(self):
        records = self.audit["_callback_filter_records"](
            ROOT / "app" / "handlers" / "admin" / "literature_editor.py"
        )
        exact = {value for kind, value, _ in records if kind == "exact"}
        prefixes = {value for kind, value, _ in records if kind == "prefix"}
        patterns = tuple(re.compile(value) for kind, value, _ in records if kind == "regex")
        covered = self.audit["_callback_value_is_handled"]
        for callback in ("admin:literature:home", "admin:literature:new", "admin:literature:time"):
            with self.subTest(callback=callback):
                self.assertTrue(covered(callback, exact, prefixes, patterns))
        for callback in ("admin:literature:erase", "admin:literature:new:extra", "admin:literature:page:nope"):
            with self.subTest(callback=callback):
                self.assertFalse(covered(callback, exact, prefixes, patterns))


class EditorialRuntimeFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_audit_agrees_with_the_actual_registered_magic_filter(self):
        handler = next(item for item in router.callback_query.handlers if item.callback.__name__ == "editorial_action")
        for callback, expected in (
            ("admin:literature:home", True),
            ("admin:literature:new", True),
            ("admin:literature:time", True),
            ("admin:literature:page:12", True),
            ("admin:literature:new:extra", False),
            ("admin:literature:erase", False),
        ):
            with self.subTest(callback=callback):
                accepted, _ = await handler.check(SimpleNamespace(data=callback))
                self.assertEqual(bool(accepted), expected)
