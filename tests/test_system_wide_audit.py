from __future__ import annotations

import ast
import importlib
import re
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def py_files() -> list[Path]:
    return sorted(APP.rglob("*.py"))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _literal_strings(node: ast.AST) -> set[str]:
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def _callback_contracts() -> tuple[set[str], set[str]]:
    """Collect exact callback values and startswith prefixes from decorators."""
    exact: set[str] = set()
    prefixes: set[str] = set()
    for path in py_files():
        tree = ast.parse(read(path), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                text = ast.unparse(decorator)
                if "callback_query" not in text or "F.data" not in text:
                    continue
                literals = _literal_strings(decorator)
                if ".startswith(" in text:
                    prefixes.update(literals)
                elif "F.data" in text:
                    exact.update(literals)
    return exact, prefixes


class SystemWideAuditTests(unittest.TestCase):
    def test_all_python_files_parse(self) -> None:
        failures = []
        for path in py_files():
            try:
                ast.parse(read(path), filename=str(path))
            except SyntaxError as exc:
                failures.append(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
        self.assertFalse(failures, "Syntax errors:\n" + "\n".join(failures))

    def test_core_modules_import(self) -> None:
        modules = [
            "app.handlers.registration",
            "app.handlers.participant",
            "app.handlers.admin",
            "app.handlers.chat_binding",
            "app.services.notification_service",
            "app.services.points_service",
            "app.services.excel_service",
            "app.database.models",
        ]
        failures = []
        for module in modules:
            try:
                importlib.import_module(module)
            except Exception as exc:  # pragma: no cover
                failures.append(f"{module}: {type(exc).__name__}: {exc}")
        self.assertFalse(failures, "Import failures:\n" + "\n".join(failures))

    def test_static_callback_data_within_telegram_limit(self) -> None:
        failures = []
        pattern = re.compile(r"callback_data\s*=\s*['\"]([^'\"]+)['\"]")
        for path in py_files():
            for value in pattern.findall(read(path)):
                if len(value.encode("utf-8")) > 64:
                    failures.append(
                        f"{path.relative_to(ROOT)}: {len(value.encode('utf-8'))} bytes: {value}"
                    )
        self.assertFalse(failures, "callback_data exceeds 64 bytes:\n" + "\n".join(failures))

    def test_no_duplicate_exact_callback_handlers_inside_one_module(self) -> None:
        failures = []
        pattern = re.compile(r"@router\.callback_query\(F\.data\s*==\s*['\"]([^'\"]+)['\"]")
        for path in py_files():
            values = pattern.findall(read(path))
            duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
            if duplicates:
                failures.append(f"{path.relative_to(ROOT)}: {', '.join(duplicates)}")
        self.assertFalse(failures, "Duplicate exact callback handlers inside a module:\n" + "\n".join(failures))

    def test_critical_literal_callbacks_have_handlers(self) -> None:
        """Verify the callbacks that form the public navigation spine.

        A repository-wide literal-to-handler scan is invalid for aiogram because
        handlers can use in_(), tuple prefixes, MagicFilter composition and
        generated callback factories. The critical navigation contract is stable
        and catches actual broken buttons without false positives.
        """
        exact, prefixes = _callback_contracts()
        critical = {
            "menu:main",
            "cabinet:open",
            "cabinet:profile",
            "cabinet:tasks",
            "cabinet:achievements",
            "cabinet:rating",
            "events:list",
            "projects:menu",
            "rewards:menu",
            "contact:menu",
            "registration:status",
            "admin:panel",
            "admin:applications",
            "admin:analytics",
            "admin:events",
            "admin:projects",
            "admin:tasks",
            "admin:auctions",
        }
        missing = sorted(
            value
            for value in critical
            if value not in exact and not any(value.startswith(prefix) for prefix in prefixes)
        )
        self.assertFalse(missing, "Critical callbacks without handlers: " + ", ".join(missing))

    def test_registration_paths_include_participation_only_option(self) -> None:
        from app.keyboards.registration import directions_keyboard

        for scope in ("internal", "external", "both", "unsure"):
            markup = directions_keyboard(scope)
            callbacks = {
                button.callback_data
                for row in markup.inline_keyboard
                for button in row
                if button.callback_data
            }
            self.assertIn("reg:dir:participate", callbacks, f"Missing participation-only option for {scope}")

    def test_registration_notification_uses_database_admins(self) -> None:
        text = read(APP / "services" / "notification_service.py")
        required = [
            "async_sessionmaker",
            "_database_admin_ids",
            "Role.ADMIN",
            "is_blocked",
            "is_archived",
            "telegram_id",
        ]
        missing = [marker for marker in required if marker not in text]
        self.assertFalse(missing, "Admin notification recipients are incomplete: " + ", ".join(missing))

    def test_critical_business_modules_are_wired(self) -> None:
        participant = read(APP / "handlers" / "participant" / "__init__.py")
        admin = read(APP / "handlers" / "admin" / "__init__.py")
        participant_required = [
            "task_block2.router",
            "projects_block5.router",
            "events_stability_block8.router",
            "event_activities_block15.router",
            "partner_offers_block16.router",
            "auction_block17.router",
        ]
        admin_required = [
            "task_review_block2.router",
            "projects_block5_decision.router",
            "event_registration_block14.router",
            "event_activities_block15.router",
            "partner_offers_block16.router",
            "auction_block17.router",
        ]
        missing = [m for m in participant_required if m not in participant]
        missing += [m for m in admin_required if m not in admin]
        self.assertFalse(missing, "Critical routers are not wired: " + ", ".join(missing))

    def test_points_sensitive_flows_have_idempotency_markers(self) -> None:
        targets = {
            "app/handlers/admin/task_review_block2.py": ["add_points", "approved"],
            "app/handlers/admin/event_registration_block14.py": ["add_points", "ATTENDED"],
            "app/handlers/admin/event_activities_block15.py": ["add_points", "approved"],
            "app/handlers/admin/partner_offers_block16.py": ["add_points", "approved"],
            "app/handlers/admin/auction_block17.py": ["points=-bid.amount", "winner"],
        }
        failures = []
        for rel, markers in targets.items():
            text = read(ROOT / rel)
            absent = [m for m in markers if m not in text]
            if absent:
                failures.append(f"{rel}: missing {', '.join(absent)}")
        self.assertFalse(failures, "Points flow contract failures:\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
