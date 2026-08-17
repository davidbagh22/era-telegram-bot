from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.services.github_oidc_service import (
    EXPECTED_REF,
    EXPECTED_REPOSITORY,
    EXPECTED_REPOSITORY_ID,
    EXPECTED_WORKFLOW_REF,
    _require_exact_backup_claims,
)
from app.services.system_health_service import (
    HealthCheck,
    _backup_check,
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

    def test_production_config_no_longer_requires_cross_platform_backup_secret(self) -> None:
        settings = Settings(
            bot_token="1234567890:test-token",
            render_external_hostname="era-telegram-bot.onrender.com",
            miniapp_auth_secret="a" * 32,
        )
        check = asyncio.run(_configuration_check(settings))
        self.assertEqual(check.status, "ok")
        self.assertNotIn("BACKUP_REPORT_SECRET", check.detail)


class GitHubOIDCIdentityTests(unittest.TestCase):
    def _claims(self) -> dict[str, object]:
        return {
            "repository": EXPECTED_REPOSITORY,
            "repository_id": EXPECTED_REPOSITORY_ID,
            "ref": EXPECTED_REF,
            "workflow_ref": EXPECTED_WORKFLOW_REF,
            "runner_environment": "github-hosted",
            "event_name": "schedule",
        }

    def test_exact_backup_identity_is_accepted(self) -> None:
        _require_exact_backup_claims(self._claims())

    def test_wrong_repository_branch_workflow_or_runner_is_rejected(self) -> None:
        for key, value in [
            ("repository", "attacker/repo"),
            ("repository_id", "1"),
            ("ref", "refs/heads/feature"),
            ("workflow_ref", "davidbagh22/era-telegram-bot/.github/workflows/other.yml@refs/heads/main"),
            ("runner_environment", "self-hosted"),
            ("event_name", "pull_request"),
        ]:
            claims = self._claims()
            claims[key] = value
            with self.subTest(key=key), self.assertRaises(HTTPException):
                _require_exact_backup_claims(claims)


class BackupHealthTests(unittest.TestCase):
    def test_recent_verified_encrypted_github_backup_is_healthy(self) -> None:
        backup = SimpleNamespace(
            status="success",
            restore_verified_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            storage_provider="github-actions-encrypted",
        )
        session = SimpleNamespace(scalar=AsyncMock(return_value=backup))
        check = asyncio.run(_backup_check(session))
        self.assertEqual(check.status, "ok")


class SystemSchedulerTests(unittest.TestCase):
    def test_attaches_expected_jobs(self) -> None:
        scheduler = SimpleNamespace(add_job=Mock())
        settings = Settings(bot_token="1234567890:test-token")
        add_system_jobs(scheduler, SimpleNamespace(), settings, SimpleNamespace())
        ids = [call.kwargs["id"] for call in scheduler.add_job.call_args_list]
        self.assertEqual(
            ids,
            [
                "system-heartbeat",
                "system-full-diagnostic",
                "system-daily-summary",
                "configured-event-reminders",
                "event-wizard-task-sync",
                "project-scoring-reconciliation",
                "task-squad-notifications",
                "my-vector-monthly-reminders",
                "general-chat-faq-pin",
            ],
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

    def test_backup_report_requires_oidc_bearer_before_db_access(self) -> None:
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
        response = TestClient(app).post("/api/v1/internal/backup/report", json=payload)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "backup_identity_required")


if __name__ == "__main__":
    unittest.main()
