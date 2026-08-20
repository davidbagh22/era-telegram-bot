"""Regression test: `alembic upgrade head` must succeed against a brand-new
sqlite database, in a fresh process, exactly the way a developer setting up a
local dev DB would run it.

This guards against a bug where migration 0029_community_missions raised
``sqlite3.OperationalError: table community_mission_templates already
exists`` on a clean sqlite database -- even though the migration only calls
``op.create_table`` once. The root cause was that 0001_initial seeds the
schema via ``Base.metadata.create_all()`` (see its docstring / the docstring
of 0029), so on a *freshly created* sqlite database, current-model tables
such as ``community_mission_templates`` already exist by the time later
migrations run. Postgres deploys never hit this because they start from an
existing schema rather than 0001's create_all path, which is why the bug
only showed up for sqlite dev databases. The fix made 0029 (and friends)
check ``_table_exists``/``_index_names`` before creating, so upgrades are
idempotent regardless of what 0001 already created.

We shell out to a real ``python -m alembic upgrade`` subprocess (rather than
driving Alembic in-process) so this test exercises the exact code path --
including alembic/env.py's async sqlite migration runner -- that a developer
running the documented setup command actually hits.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["BOT_TOKEN"] = "1234567890:test-token"
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


class AlembicFreshSqliteUpgradeTests(unittest.TestCase):
    def test_upgrade_head_succeeds_on_fresh_sqlite_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "fresh.db"
            result = _run_alembic("upgrade", "head", db_path=db_path)
            self.assertEqual(
                result.returncode,
                0,
                msg=f"alembic upgrade head failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            self.assertTrue(db_path.exists())

    def test_upgrade_to_0029_in_isolated_second_process_succeeds(self) -> None:
        """Literal regression repro: upgrade to 0028 in one process, then
        upgrade the same database file to 0029 in a brand-new process.
        Previously this failed with ``table community_mission_templates
        already exists`` even though the migration only creates it once.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "fresh.db"

            first = _run_alembic("upgrade", "0028_recognition_opportunities", db_path=db_path)
            self.assertEqual(
                first.returncode,
                0,
                msg=f"alembic upgrade to 0028 failed:\nSTDOUT:\n{first.stdout}\nSTDERR:\n{first.stderr}",
            )

            second = _run_alembic("upgrade", "0029_community_missions", db_path=db_path)
            self.assertEqual(
                second.returncode,
                0,
                msg=f"alembic upgrade to 0029 failed:\nSTDOUT:\n{second.stdout}\nSTDERR:\n{second.stderr}",
            )
            self.assertNotIn("already exists", second.stderr)


if __name__ == "__main__":
    unittest.main()
