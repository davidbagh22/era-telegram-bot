from __future__ import annotations

import re
import runpy
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace

from app.handlers.admin.literature_editor import router

ROOT = Path(__file__).resolve().parents[1]


class StaticCallbackAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = ROOT / "system_audit_report.json"
        previous = report.read_bytes() if report.exists() else None
        def restore_report():
            if previous is None:
                report.unlink(missing_ok=True)
            else:
                report.write_bytes(previous)
        cls.addClassCleanup(restore_report)
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

    def test_nondefault_regexp_options_do_not_prove_unreachable_callback_coverage(self):
        source = """
@router.callback_query(F.data.regexp("foo", mode="fullmatch"))
async def full(): pass
@router.callback_query(F.data.regexp("foo", mode="search"))
async def search_mode(): pass
@router.callback_query(F.data.regexp("foo", search=True))
async def old_search(): pass
@router.callback_query(F.data.regexp("foo", flags=re.I))
async def insensitive(): pass
@router.callback_query(F.data.regexp("^default-only$"))
async def normal(): pass
"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "handlers.py"
            path.write_text(source)
            records = self.audit["_callback_filter_records"](path)
        assert [(kind, pattern) for kind, pattern, _ in records] == [("regex", "^default-only$")]
        patterns = tuple(re.compile(pattern) for kind, pattern, _ in records if kind == "regex")
        covered = self.audit["_callback_value_is_handled"]
        assert covered("default-only", set(), set(), patterns)
        assert not covered("foobar", set(), set(), patterns)


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
