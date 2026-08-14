from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.services.system_health_service import HealthCheck, _score, sanitize_runtime_detail
from app.services.system_scheduler import add_system_jobs


class SystemSanitizerTests(unittest.TestCase):
    def test_redacts_common_secret_shapes(self) -> None:
        raw = (
            "token=super-secret-value password=hunter2 "
            "postgresql+asyncpg://user:pass@db.example/era "
            "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
        )
        cleaned = sanitize_runtime_detail(raw)
        self.assertNotIn("super-secret-value", cleaned)
        self.assertNotIn("hunter2", cleaned)
        self.assertNotIn("user:pass", cleaned)
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZ", cleaned)
        self.assertIn("REDACTED", cleaned)

    def test_health_score_marks_critical(self) -> None:
        score, status = _score(
            [HealthCheck("db", "DB", "error", "critical", "down")]
        )
        self.assertEqual(status, "critical")
        self.assertLess(score, 100)


class SystemSchedulerTests(unittest.TestCase):
    def test_attaches_expected_jobs(self) -> None:
        scheduler = SimpleNamespace(add_job=unittest.mock.Mock())
        settings = Settings(bot_token="1234567890:test-token")
        add_system_jobs(scheduler, SimpleNamespace(), settings, SimpleNamespace())
        ids = [call.kwargs["id"] for call in scheduler.add_job.call_args_list]
        self.assertEqual(
            ids,
            ["system-heartbeat", "system-full-diagnostic", "system-daily-summary"],
        )


class SystemApiAuthorizationTests(unittest.TestCase):
    def _app(self, user) -> FastAPI:
        app = FastAPI()
        app.include_router(api_router)

        async def session_override():
            yield SimpleNamespace()

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token"
        )
        app.dependency_overrides[get_bot] = lambda: None
        return app

    def test_participant_cannot_read_system_snapshot(self) -> None:
        participant = SimpleNamespace(
            id=2,
            telegram_id=777,
            role="participant",
            is_blocked=False,
            is_archived=False,
            permission_grants=[],
        )
        response = TestClient(self._app(participant)).get("/api/v1/admin/system")
        self.assertEqual(response.status_code, 403)

    def test_backup_report_rejects_invalid_secret_before_db_access(self) -> None:
        app = self._app(
            SimpleNamespace(
                id=1,
                telegram_id=555,
                role="admin",
                is_blocked=False,
                is_archived=False,
                permission_grants=[],
            )
        )
        payload = {
            "backup_key": "era-backup-test",
            "status": "failed",
            "backup_type": "daily",
        }
        with patch.dict(os.environ, {"BACKUP_REPORT_SECRET": "correct-secret"}, clear=False):
            response = TestClient(app).post(
                "/api/v1/internal/backup/report",
                headers={"X-ERA-Backup-Secret": "wrong-secret"},
                json=payload,
            )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
