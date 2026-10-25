from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from scripts import e2e_seed


class SeedSafetyTests(IsolatedAsyncioTestCase):
    async def test_fixture_seed_rejects_production_and_unrelated_local_databases(self):
        for render, dev, database in (
            (True, True, "sqlite+aiosqlite:///e2e.db"),
            (False, False, "sqlite+aiosqlite:///e2e.db"),
            (False, True, "postgresql+asyncpg://localhost/production"),
            (False, True, "sqlite+aiosqlite:///era.db"),
        ):
            settings = SimpleNamespace(is_render_deployment=render, dev_auth_enabled=dev, database_url=database)
            with self.subTest(render=render, dev=dev, database=database), patch.object(e2e_seed, "get_settings", return_value=settings), patch.object(e2e_seed, "create_engine_and_sessionmaker") as create:
                with self.assertRaises(RuntimeError):
                    await e2e_seed.seed()
                create.assert_not_called()
