from __future__ import annotations

import io
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.v1.admin_applications import FullApplicationOut, _load_photo_data_url
from app.api.v1.router import api_router
from app.config import Settings


class FullAdminApplicationViewTests(unittest.IsolatedAsyncioTestCase):
    def test_full_application_contract_contains_registration_data(self) -> None:
        fields = set(FullApplicationOut.model_fields)
        required = {
            "telegram_id",
            "username",
            "first_name",
            "last_name",
            "birth_date",
            "age",
            "phone",
            "email",
            "city",
            "education_work",
            "occupation",
            "skills",
            "experience",
            "motivation",
            "available_time",
            "desired_path",
            "departments",
            "directions",
            "social_links",
            "personal_data_consent",
            "consent_policy_version",
            "application_status",
            "photo_attached",
            "photo_data_url",
            "created_at",
        }
        self.assertTrue(required.issubset(fields))
        self.assertNotIn("photo_file_id", fields)

    def test_http_endpoint_serves_full_application_contract(self) -> None:
        app = FastAPI()
        app.include_router(api_router)
        admin = SimpleNamespace(
            id=1,
            telegram_id=555,
            role="admin",
            is_blocked=False,
            is_archived=False,
            permission_grants=[],
        )
        pending = SimpleNamespace(id=42)
        rows = SimpleNamespace(all=lambda: [pending])
        session = SimpleNamespace(scalars=AsyncMock(return_value=rows))

        async def _session_override():
            yield session

        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_settings] = lambda: Settings(
            bot_token="1234567890:test-token"
        )
        app.dependency_overrides[get_bot] = lambda: None

        full = FullApplicationOut(
            id=42,
            telegram_id=777001,
            username="pending_member",
            first_name="Новый",
            last_name="Участник",
            birth_date="2000-01-01",
            age=26,
            phone="+37400000000",
            email="member@example.test",
            city="Ереван",
            education_work="Университет",
            occupation="Студент",
            skills=["Организация"],
            experience="Волонтёрство",
            motivation="Хочу развиваться в ЭРА",
            available_time="3–5 часов в неделю",
            desired_path="Активист",
            departments=["Внутренние связи"],
            directions=["Культура"],
            social_links=[{"platform": "Telegram", "url": "https://t.me/pending_member"}],
            personal_data_consent=True,
            consent_policy_version="era-personal-data-v1",
            application_status="pending",
            photo_attached=True,
            photo_data_url="data:image/jpeg;base64,ZmFrZQ==",
            created_at="2026-08-15T00:00:00+00:00",
        )

        with patch(
            "app.api.v1.admin_applications._application_out",
            new=AsyncMock(return_value=full),
        ) as application_out:
            response = TestClient(app).get("/api/v1/admin/applications")

        self.assertEqual(response.status_code, 200)
        application_out.assert_awaited_once()
        payload = response.json()[0]
        self.assertEqual(payload["phone"], "+37400000000")
        self.assertEqual(payload["departments"], ["Внутренние связи"])
        self.assertEqual(payload["directions"], ["Культура"])
        self.assertTrue(payload["personal_data_consent"])
        self.assertTrue(payload["photo_attached"])
        self.assertTrue(payload["photo_data_url"].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("photo_file_id", payload)

    async def test_photo_is_embedded_without_exposing_telegram_file_id(self) -> None:
        bot = AsyncMock()
        bot.download.return_value = io.BytesIO(b"fake-jpeg-bytes")
        profile = SimpleNamespace(photo_file_id="telegram-file-id-must-stay-server-side")

        result = await _load_photo_data_url(bot, profile, user_id=42)

        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("data:image/jpeg;base64,"))
        self.assertNotIn("telegram-file-id-must-stay-server-side", result)
        bot.download.assert_awaited_once_with("telegram-file-id-must-stay-server-side")

    async def test_photo_failure_does_not_break_application_queue(self) -> None:
        bot = AsyncMock()
        bot.download.side_effect = RuntimeError("simulated telegram failure")
        profile = SimpleNamespace(photo_file_id="telegram-file-id")

        result = await _load_photo_data_url(bot, profile, user_id=42)

        self.assertIsNone(result)

    def test_admin_screen_renders_photo_and_full_sections(self) -> None:
        source = Path("frontend/src/screens/admin/AdminApplicationsScreen.tsx").read_text(
            encoding="utf-8"
        )
        for marker in (
            "application.photo_data_url",
            "Личные данные",
            "Контакты",
            "Учёба и деятельность",
            "Интерес к ЭРА",
            "Мотивация",
            "Согласие и подача",
            "application.social_links",
            "application.birth_date",
            "application.available_time",
            "application.desired_path",
        ):
            self.assertIn(marker, source)

    def test_admin_screen_can_delete_application_safely(self) -> None:
        source = Path("frontend/src/screens/admin/AdminApplicationsScreen.tsx").read_text(
            encoding="utf-8"
        )
        for marker in (
            "Удалить анкету",
            "window.confirm",
            "setUserArchived",
            "await setUserArchived(userId, true)",
            "Она исчезнет из очереди заявок",
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
