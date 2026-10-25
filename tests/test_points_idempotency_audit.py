import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python_files() -> list[Path]:
    return [path for path in (ROOT / "app").rglob("*.py") if path.is_file()]


def test_every_add_points_call_has_idempotency_key() -> None:
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Name) or func.id != "add_points":
                continue
            keywords = {keyword.arg for keyword in node.keywords if keyword.arg}
            if "idempotency_key" not in keywords:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == []


def test_point_transactions_are_created_only_in_points_service() -> None:
    offenders: list[str] = []
    allowed = Path("app/services/points_service.py")
    for path in _python_files():
        if path.relative_to(ROOT) == allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "PointTransaction":
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == []
