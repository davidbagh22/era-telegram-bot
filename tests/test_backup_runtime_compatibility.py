import unittest
from unittest.mock import AsyncMock, patch

from app.services.backup_runtime_service import (
    BackupSnapshotError,
    verify_pg_dump_compatibility,
)


class BackupRuntimeCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_pg_dump_older_than_server_without_exposing_credentials(self) -> None:
        capture = AsyncMock(side_effect=["pg_dump (PostgreSQL) 17.10", "180000"])
        with patch("app.services.backup_runtime_service._capture", capture):
            with self.assertRaisesRegex(
                BackupSnapshotError,
                r"^pg_dump_client_too_old_client_17_server_18$",
            ) as raised:
                await verify_pg_dump_compatibility(
                    "postgresql://era:super-secret@private-db/era"
                )
        self.assertNotIn("super-secret", str(raised.exception))
        self.assertNotIn("private-db", str(raised.exception))

    async def test_accepts_matching_pg_dump_and_server_major(self) -> None:
        capture = AsyncMock(side_effect=["pg_dump (PostgreSQL) 18.1", "180001"])
        with patch("app.services.backup_runtime_service._capture", capture):
            self.assertEqual(
                await verify_pg_dump_compatibility("postgresql://era:secret@db/era"),
                (18, 18),
            )

    async def test_accepts_newer_client_for_older_server(self) -> None:
        capture = AsyncMock(side_effect=["pg_dump (PostgreSQL) 18.1", "170006"])
        with patch("app.services.backup_runtime_service._capture", capture):
            self.assertEqual(
                await verify_pg_dump_compatibility("postgresql://era:secret@db/era"),
                (18, 17),
            )


if __name__ == "__main__":
    unittest.main()
