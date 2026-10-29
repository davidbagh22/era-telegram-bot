"""Missing media identity must fail closed without touching persistence."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from app.services.media_workspace_service import require_access


class MediaWorkspaceMissingActorTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_actor_rejected_for_read_and_write_without_database_calls(self):
        for write, area in ((False, None), (True, "era"), (True, "ksoors")):
            with self.subTest(write=write, area=area):
                session = MagicMock()
                session.scalar = AsyncMock()
                with self.assertRaises(PermissionError):
                    await require_access(session, None, None, write=write, area=area)
                session.scalar.assert_not_awaited()
                session.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
