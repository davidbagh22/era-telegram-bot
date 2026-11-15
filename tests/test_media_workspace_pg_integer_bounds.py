"""Reject out-of-range media workspace IDs before PostgreSQL INTEGER binds.

Pure ASGI/Pydantic validation: no real DB, user, Telegram or role mutation.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.media_workspace import (
    CalendarCreate,
    CalendarUpdate,
    EditorChange,
    PG_INTEGER_MAX,
    router,
)


class MediaWorkspacePgIntegerBoundaryTests(unittest.TestCase):
    def test_model_ids_reject_postgres_integer_overflow(self):
        payload = {
            "request_key": "00000000-0000-4000-8000-000000000001",
            "title": "Тестовый материал",
        }
        for model, field, base in (
            (CalendarCreate, "responsible_id", payload),
            (CalendarUpdate, "responsible_id", {"revision": 0}),
            (EditorChange, "user_id", {"enabled": True, "revision": 0}),
        ):
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    getattr(model.model_validate({**base, field: PG_INTEGER_MAX}), field),
                    PG_INTEGER_MAX,
                )
                for invalid in (0, -1, PG_INTEGER_MAX + 1, 10**80):
                    with self.subTest(invalid=invalid):
                        with self.assertRaises(ValidationError):
                            model.model_validate({**base, field: invalid})

    def test_invalid_path_query_ids_rejected_before_service_or_db(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        app.dependency_overrides[get_session] = lambda: SimpleNamespace()
        app.dependency_overrides[get_settings] = lambda: SimpleNamespace()

        with (
            patch("app.api.v1.media_workspace.service.require_access", new_callable=AsyncMock) as access,
            patch("app.api.v1.media_workspace.service.calendar", new_callable=AsyncMock) as calendar,
            patch("app.api.v1.media_workspace.service.update_entry", new_callable=AsyncMock) as update,
            TestClient(app) as client,
        ):
            for value in (0, -1, PG_INTEGER_MAX + 1, 10**80):
                with self.subTest(value=value):
                    get_response = client.get(
                        "/media/workspaces/era/calendar",
                        params={"before_id": str(value)},
                    )
                    patch_response = client.patch(
                        f"/media/workspaces/era/calendar/{value}",
                        json={"revision": 0, "status": "ready"},
                    )
                    self.assertEqual(get_response.status_code, 422, get_response.text)
                    self.assertEqual(patch_response.status_code, 422, patch_response.text)
            access.assert_not_awaited()
            calendar.assert_not_awaited()
            update.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
