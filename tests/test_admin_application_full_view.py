from __future__ import annotations

import io
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.api.v1.admin_applications import FullApplicationOut, _load_photo_data_url
from app.api.v1.router import api_router


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

    def test_full_route_precedes_legacy_compact_route(self) -> None:
        # Test endpoint registration order rather than the router's internal
        # rendered path string: FastAPI can rewrite prefixes during nested
        # include_router calls, while first-match ordering is what determines
        # which GET implementation serves Admin Mode.
        get_routes = [
            route
            for route in api_router.routes
            if "GET" in (getattr(route, "methods", None) or set())
        ]
        full_indexes = [
            index
            for index, route in enumerate(get_routes)
            if getattr(getattr(route, "endpoint", None), "__module__", "")
            == "app.api.v1.admin_applications"
        ]
        compact_indexes = [
            index
            for index, route in enumerate(get_routes)
            if getattr(getattr(route, "endpoint", None), "__module__", "")
            == "app.api.v1.admin"
            and getattr(getattr(route, "endpoint", None), "__name__", "")
            == "read_applications"
        ]
        self.assertEqual(len(full_indexes), 1)
        if compact_indexes:
            self.assertLess(full_indexes[0], compact_indexes[0])

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


if __name__ == "__main__":
    unittest.main()
