from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.services.system_health_service import (
    HealthCheck,
    _chat_config_check,
    _configuration_check,
    _score,
    sanitize_runtime_detail,
)
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


class SystemConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_backup_report_secret_is_not_required_for_production_health(self) -> None:
        settings = Settings(
            bot_token="1234567890:test-token",
            render_external_hostname="era.example",
            miniapp_auth_secret="miniapp-auth-secret",
            backup_report_secret="",
        )
        result = await _configuration_check(settings)
        self.assertEqual(result.status, "ok")
        self.assertNotIn("BACKUP_REPORT_SECRET", result.detail)

    async def test_real_auth_secret_is_still_required_on_render(self) -> None:
        settings = Settings(
            bot_token="1234567890:test-token",
            render_external_hostname="era.example",
            miniapp_auth_secret="",
            backup_report_secret="",
        )
        result = await _configuration_check(settings)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.severity, "critical")
        self.assertIn("MINIAPP_AUTH_SECRET", result.detail)

    async def test_all_four_bound_chats_make_chat_health_green(self) -> None:
        settings = Settings(
            bot_token="1234567890:test-token",
            general_chat_id=-100001,
            internal_department_chat_id=-100002,
            external_department_chat_id=-100003,
            leaders_chat_id=-100004,
        )
        result = await _chat_config_check(settings)
        self.assertEqual(result.status, "ok")
        self.assertIn("Все четыре", result.detail)

    async def test_missing_chat_ids_explain_bind_action_without_guessing_ids(self) -> None:
        settings = Settings(bot_token="1234567890:test-token")
        result = await _chat_config_check(settings)
        self.assertEqual(result.status, "warning")
        self.assertEqual(result.severity, "medium")
        self.assertIn("/bind", result.detail)
        for key in ("general", "internal", "external", "leaders"):
            self.assertIn(key, result.detail)


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
    def _app(self, user, *, backup_report_secret: str = "") -> FastAPI:
        app = FastAPI()
        app.include_router(api_router)

        async def session_override():
            yield SimpleNamespace()

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token",
            backup_report_secret=backup_report_secret,
        )
        app.dependency_overrides[get_bot] = lambda: None
        return app

    @staticmethod
    def _admin():
        return SimpleNamespace(
            id=1,
            telegram_id=555,
            role="admin",
            is_blocked=False,
            is_archived=False,
            permission_grants=[],
        )

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

    def test_backup_report_stays_fail_closed_when_optional_secret_is_absent(self) -> None:
        payload = {
            "backup_key": "era-backup-test",
            "status": "failed",
            "backup_type": "daily",
        }
        response = TestClient(self._app(self._admin())).post(
            "/api/v1/internal/backup/report",
            headers={"X-ERA-Backup-Secret": "anything"},
            json=payload,
        )
        self.assertEqual(response.status_code, 503)

    def test_backup_report_rejects_invalid_secret_before_db_access(self) -> None:
        payload = {
            "backup_key": "era-backup-test",
            "status": "failed",
            "backup_type": "daily",
        }
        with patch.dict(os.environ, {"BACKUP_REPORT_SECRET": "correct-secret"}, clear=False):
            response = TestClient(
                self._app(self._admin(), backup_report_secret="correct-secret")
            ).post(
                "/api/v1/internal/backup/report",
                headers={"X-ERA-Backup-Secret": "wrong-secret"},
                json=payload,
            )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()