from __future__ import annotations

import ast
import importlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

issues: list[dict] = []
checks: list[dict] = []


def add_check(name: str, ok: bool, details=None) -> None:
    checks.append({"name": name, "ok": ok, "details": details or []})
    if not ok:
        issues.append({"check": name, "details": details or []})


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _imported_handler_files(path: Path) -> set[Path]:
    """Resolve statically imported handler modules from a router composition file."""
    result: set[Path] = set()
    tree = ast.parse(read(path), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not node.module.startswith("app.handlers"):
            continue
        base = ROOT / node.module.replace(".", "/")
        for alias in node.names:
            candidate = base / f"{alias.name}.py"
            if candidate.exists():
                result.add(candidate)
    return result


def active_handler_files() -> set[Path]:
    """Return only handler modules reachable from the real dispatcher.

    Historical fallback modules may stay in the repository for migration
    reference, but only routers mounted from app.bot / package composition are
    treated as live UI owners.
    """
    active: set[Path] = set()
    active.update(_imported_handler_files(APP / "bot.py"))
    for package in ("admin", "leader", "participant"):
        active.update(_imported_handler_files(APP / "handlers" / package / "__init__.py"))
    return {path for path in active if path.exists()}


def _string_set_constants(tree: ast.AST) -> dict[str, set[str]]:
    """Collect simple module-level string set/tuple/list constants.

    This lets the callback audit understand production patterns such as
    ``F.data.in_(LEGACY_ADMIN_ACTIONS)`` instead of reporting their buttons as
    dead merely because the strings live one line above the decorator.
    """
    result: dict[str, set[str]] = {}
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        target = node.targets[0] if isinstance(node, ast.Assign) and node.targets else getattr(node, "target", None)
        value = node.value
        if not isinstance(target, ast.Name) or not isinstance(value, (ast.Set, ast.Tuple, ast.List)):
            continue
        values = {
            item.value
            for item in value.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        }
        if values and len(values) == len(value.elts):
            result[target.id] = values
    return result


def _callback_filter_records(path: Path) -> list[tuple[str, str, str]]:
    """Return (kind, value, full-filter-signature) for callback decorators."""
    records: list[tuple[str, str, str]] = []
    try:
        tree = ast.parse(read(path), filename=str(path))
    except SyntaxError:
        return records
    constants = _string_set_constants(tree)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for decorator in node.decorator_list:
            try:
                signature = ast.unparse(decorator)
            except Exception:
                continue
            if "callback_query" not in signature or "F.data" not in signature:
                continue
            for value in re.findall(r"F\.data\s*==\s*['\"]([^'\"]+)['\"]", signature):
                records.append(("exact", value, signature))
            for value in re.findall(r"F\.data\.startswith\(['\"]([^'\"]+)['\"]\)", signature):
                records.append(("prefix", value, signature))
            if "F.data.in_(" in signature:
                literal_values = re.findall(r"['\"]([^'\"]+)['\"]", signature)
                for value in literal_values:
                    records.append(("exact", value, signature))
                match = re.search(r"F\.data\.in_\(([A-Za-z_][A-Za-z0-9_]*)\)", signature)
                if match:
                    for value in sorted(constants.get(match.group(1), set())):
                        records.append(("exact", value, signature))
    return records


files = sorted(APP.rglob("*.py"))
active_handlers = active_handler_files()

syntax_errors = []
for path in files:
    try:
        ast.parse(read(path), filename=str(path))
    except SyntaxError as exc:
        syntax_errors.append(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
add_check("Python syntax", not syntax_errors, syntax_errors)

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
import_errors = []
for module in modules:
    try:
        importlib.import_module(module)
    except Exception as exc:
        import_errors.append(f"{module}: {type(exc).__name__}: {exc}")
add_check("Core imports", not import_errors, import_errors)

sources = {path: read(path) for path in files}
button_pattern = re.compile(r"callback_data\s*=\s*['\"]([^'\"]+)['\"]")

long_callbacks = []
for path, text in sources.items():
    for value in button_pattern.findall(text):
        size = len(value.encode("utf-8"))
        if size > 64:
            long_callbacks.append(f"{path.relative_to(ROOT)}: {size} bytes: {value}")
add_check("Telegram callback_data length", not long_callbacks, long_callbacks)

# Duplicate handlers only matter when both modules are actually mounted. The
# full filter signature is part of the identity so state-scoped variants are
# not mistaken for a duplicate merely because they share a callback string.
handler_records: list[tuple[str, str, str, Path]] = []
for path in active_handlers:
    for kind, value, signature in _callback_filter_records(path):
        handler_records.append((kind, value, signature, path))

exact_records = [row for row in handler_records if row[0] == "exact"]
identity_counts = Counter((value, signature) for _, value, signature, _ in exact_records)
duplicates = []
for (value, signature), count in identity_counts.items():
    if count <= 1:
        continue
    paths = sorted(
        str(path.relative_to(ROOT))
        for _, callback, sig, path in exact_records
        if callback == value and sig == signature
    )
    duplicates.append(f"{value}: {', '.join(paths)}")
add_check("Duplicate active callback handlers", not duplicates, duplicates)

exact_handlers = {value for kind, value, _, _ in handler_records if kind == "exact"}
prefixes = {value for kind, value, _, _ in handler_records if kind == "prefix"}

# Buttons embedded in active handlers and shared keyboard modules are reachable
# UI. Buttons sitting only in unmounted historical handlers are not.
button_sources: dict[Path, str] = {path: read(path) for path in active_handlers}
for path in sorted((APP / "keyboards").rglob("*.py")):
    button_sources[path] = read(path)

missing_handlers = []
for path, text in button_sources.items():
    for value in button_pattern.findall(text):
        if value in {"noop", "ignore"}:
            continue
        if value in exact_handlers or any(value.startswith(prefix) for prefix in prefixes):
            continue
        missing_handlers.append(f"{path.relative_to(ROOT)} -> {value}")
add_check(
    "Reachable literal callback buttons have handlers",
    not missing_handlers,
    sorted(set(missing_handlers)),
)

try:
    from app.keyboards.registration import directions_keyboard

    missing_scope = []
    for scope in ("internal", "external", "both", "unsure"):
        callbacks = {
            button.callback_data
            for row in directions_keyboard(scope).inline_keyboard
            for button in row
            if button.callback_data
        }
        if "reg:dir:participate" not in callbacks:
            missing_scope.append(scope)
    add_check("Participation-only registration path", not missing_scope, missing_scope)
except Exception as exc:
    add_check("Participation-only registration path", False, [str(exc)])

notification = read(APP / "services" / "notification_service.py")
notification_markers = [
    "_database_admin_ids",
    "Role.ADMIN",
    "is_blocked",
    "is_archived",
    "telegram_id",
    "admin_notification_recipients",
]
notification_missing = [marker for marker in notification_markers if marker not in notification]
add_check("Admin application recipients", not notification_missing, notification_missing)

participant = read(APP / "handlers" / "participant" / "__init__.py")
admin = read(APP / "handlers" / "admin" / "__init__.py")
router_markers = [
    (participant, "task_block2.router"),
    (participant, "projects_block5.router"),
    (participant, "events_stability_block8.router"),
    (participant, "event_activities_block15.router"),
    (participant, "partner_offers_block16.router"),
    (participant, "auction_block17.router"),
    (admin, "task_review_block2.router"),
    (admin, "projects_block5_decision.router"),
    (admin, "event_registration_block14.router"),
    (admin, "event_activities_block7.router"),
    (admin, "partner_offers_block16.router"),
    (admin, "auction_block17.router"),
]
missing_routers = [marker for text, marker in router_markers if marker not in text]
add_check("Critical routers wired", not missing_routers, missing_routers)

# The MASTER architecture requires one verified-activity scoring gateway. Do
# not require handlers to call add_points directly: that would encourage a
# second points engine and skip metrics/rank/lifecycle side effects.
scoring_contracts = {
    "app/services/activity_scoring_service.py": [
        "record_verified_activity",
        "score_event_attendance_and_role",
        "score_task_completion",
        "score_project_completion",
        "idempotency_key",
    ],
    "app/services/task_review_service.py": ["score_task_completion"],
    "app/services/event_registration_service.py": ["score_event_attendance_and_role"],
    "app/services/event_activity_scoring_service.py": [
        "score_event_activity_completion",
        "record_verified_activity",
    ],
    "app/services/project_scoring_reconciliation_service.py": ["score_project_completion"],
}
scoring_failures = []
for rel, markers in scoring_contracts.items():
    text = read(ROOT / rel)
    absent = [marker for marker in markers if marker not in text]
    if absent:
        scoring_failures.append(f"{rel}: missing {', '.join(absent)}")
add_check("Verified activity uses single scoring pipeline", not scoring_failures, scoring_failures)

report = {
    "summary": {
        "checks": len(checks),
        "passed": sum(1 for check in checks if check["ok"]),
        "failed": sum(1 for check in checks if not check["ok"]),
    },
    "active_handler_files": sorted(str(path.relative_to(ROOT)) for path in active_handlers),
    "checks": checks,
    "issues": issues,
    "limitations": [
        "Real Telegram API delivery requires a live bot test.",
        "Render deployment and production environment variables are not exercised by repository CI.",
        "Database race conditions require integration tests against PostgreSQL with concurrent requests.",
        "FSM persistence across a Render restart requires a live restart test.",
    ],
}
(ROOT / "system_audit_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report["summary"], ensure_ascii=False))
