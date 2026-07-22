from __future__ import annotations

import ast
import importlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
issues: list[dict] = []
checks: list[dict] = []


def add_check(name: str, ok: bool, details=None) -> None:
    checks.append({"name": name, "ok": ok, "details": details or []})
    if not ok:
        issues.append({"check": name, "details": details or []})


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


files = sorted(APP.rglob("*.py"))

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
all_source = "\n".join(sources.values())

long_callbacks = []
button_pattern = re.compile(r"callback_data\s*=\s*['\"]([^'\"]+)['\"]")
for path, text in sources.items():
    for value in button_pattern.findall(text):
        size = len(value.encode("utf-8"))
        if size > 64:
            long_callbacks.append(f"{path.relative_to(ROOT)}: {size} bytes: {value}")
add_check("Telegram callback_data length", not long_callbacks, long_callbacks)

exact_found = []
exact_pattern = re.compile(r"@router\.callback_query\(F\.data\s*==\s*['\"]([^'\"]+)['\"]")
for path, text in sources.items():
    for value in exact_pattern.findall(text):
        exact_found.append((value, str(path.relative_to(ROOT))))
counts = Counter(value for value, _ in exact_found)
duplicates = []
for value, count in counts.items():
    if count > 1:
        duplicates.append(f"{value}: " + ", ".join(path for callback, path in exact_found if callback == value))
add_check("Duplicate exact callback handlers", not duplicates, duplicates)

exact_handlers = set(re.findall(r"F\.data\s*==\s*['\"]([^'\"]+)['\"]", all_source))
prefixes = set(re.findall(r"F\.data\.startswith\(['\"]([^'\"]+)['\"]\)", all_source))
missing_handlers = []
for path, text in sources.items():
    for value in button_pattern.findall(text):
        if value in {"noop", "ignore"}:
            continue
        if value in exact_handlers or any(value.startswith(prefix) for prefix in prefixes):
            continue
        missing_handlers.append(f"{path.relative_to(ROOT)} -> {value}")
add_check("Literal callback buttons have handlers", not missing_handlers, sorted(set(missing_handlers)))

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
notification_missing = [m for m in ["AsyncSession", "Role.ADMIN", "is_blocked", "is_archived", "telegram_id"] if m not in notification]
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
    (admin, "event_activities_block15.router"),
    (admin, "partner_offers_block16.router"),
    (admin, "auction_block17.router"),
]
missing_routers = [marker for text, marker in router_markers if marker not in text]
add_check("Critical routers wired", not missing_routers, missing_routers)

points_targets = {
    "app/handlers/admin/task_review_block2.py": ["add_points", "approved"],
    "app/handlers/admin/event_registration_block14.py": ["add_points", "ATTENDED"],
    "app/handlers/admin/event_activities_block15.py": ["add_points", "approved"],
    "app/handlers/admin/partner_offers_block16.py": ["add_points", "approved"],
    "app/handlers/admin/auction_block17.py": ["points=-winner_bid.amount", "winner"],
}
points_failures = []
for rel, markers in points_targets.items():
    text = read(ROOT / rel)
    absent = [m for m in markers if m not in text]
    if absent:
        points_failures.append(f"{rel}: missing {', '.join(absent)}")
add_check("Points-sensitive flow contracts", not points_failures, points_failures)

report = {
    "summary": {
        "checks": len(checks),
        "passed": sum(1 for c in checks if c["ok"]),
        "failed": sum(1 for c in checks if not c["ok"]),
    },
    "checks": checks,
    "issues": issues,
    "limitations": [
        "Real Telegram API delivery requires a live bot test.",
        "Render deployment and production environment variables are not exercised by repository CI.",
        "Database race conditions require integration tests against PostgreSQL with concurrent requests.",
        "FSM persistence across a Render restart requires a live restart test.",
    ],
}
(ROOT / "system_audit_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report["summary"], ensure_ascii=False))
