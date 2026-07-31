from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = ROOT / "alembic" / "versions"
MAX_ALEMBIC_VERSION_LENGTH = 32


def _metadata(path: Path) -> tuple[str | None, str | tuple[str, ...] | None]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    revision = None
    down_revision = None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "revision":
                revision = ast.literal_eval(node.value)
            elif target.id == "down_revision":
                down_revision = ast.literal_eval(node.value)
    return revision, down_revision


def _migration_metadata() -> dict[Path, tuple[str | None, str | tuple[str, ...] | None]]:
    return {
        path: _metadata(path)
        for path in sorted(VERSIONS_DIR.glob("*.py"))
        if path.name != "__init__.py"
    }


def test_revision_ids_fit_alembic_version_column() -> None:
    failures: list[str] = []
    for path, (revision, _) in _migration_metadata().items():
        if not revision:
            failures.append(f"{path.name}: missing revision")
            continue
        if len(revision) > MAX_ALEMBIC_VERSION_LENGTH:
            failures.append(
                f"{path.name}: revision {revision!r} is {len(revision)} chars; "
                f"max is {MAX_ALEMBIC_VERSION_LENGTH}"
            )
    assert failures == [], "Invalid Alembic revision ids:\n" + "\n".join(failures)


def test_down_revisions_reference_existing_revision_ids() -> None:
    metadata = _migration_metadata()
    revisions = {revision for revision, _ in metadata.values() if revision}
    missing: list[str] = []

    for path, (_, down_revision) in metadata.items():
        if down_revision is None:
            continue
        parents = down_revision if isinstance(down_revision, tuple) else (down_revision,)
        for parent in parents:
            if parent not in revisions:
                missing.append(f"{path.name}: missing parent {parent!r}")

    assert missing == [], "Broken Alembic revision graph:\n" + "\n".join(missing)


def test_alembic_graph_has_single_head() -> None:
    metadata = _migration_metadata()
    revisions = {revision for revision, _ in metadata.values() if revision}
    referenced: set[str] = set()

    for _, down_revision in metadata.values():
        if down_revision is None:
            continue
        if isinstance(down_revision, tuple):
            referenced.update(down_revision)
        else:
            referenced.add(down_revision)

    heads = sorted(revisions - referenced)
    assert len(heads) == 1, f"Expected one Alembic head, got {heads}"
