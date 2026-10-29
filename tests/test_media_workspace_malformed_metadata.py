"""Malformed legacy media JSON must not break calendar reads or be rewritten.

Isolated tests: no production DB, users, Telegram messages, or permissions.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import media_workspace_service as service


def _item(metadata):
    return SimpleNamespace(
        id=42, metadata_json=metadata, scheduled_at=None, title="Материал",
        rubric=None, body="", status="planned",
    )


class MalformedCalendarMetadataTests(unittest.TestCase):
    def test_read_only_serialization_tolerates_non_object_legacy_json(self):
        for malformed in (None, [], ["x"], "legacy", 7, True):
            with self.subTest(metadata=malformed):
                item = _item(malformed)
                self.assertEqual(service.area_of(item), "era")
                result = service.item_out(item)
                self.assertEqual(result["id"], 42)
                self.assertEqual(result["area"], "era")
                self.assertEqual(result["revision"], 0)
                self.assertEqual(result["platform"], "telegram")
                self.assertIsNone(result["responsible_id"])
                self.assertEqual(item.metadata_json, malformed)

    def test_valid_metadata_is_preserved(self):
        item = _item({"media_area": "ksoors", "workspace_revision": 3, "platform": "instagram"})
        self.assertEqual(service.area_of(item), "ksoors")
        self.assertEqual(service.item_out(item)["revision"], 3)
        self.assertEqual(service.item_out(item)["platform"], "instagram")


class MalformedCalendarMetadataReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_calendar_excludes_non_object_json_without_hiding_healthy_rows(self):
        good = _item({"media_area": "era", "workspace_revision": 2})
        good.id = 43
        legacy_null = _item(None)
        legacy_null.id = 44
        corrupt = _item(["unscoped"])
        session = SimpleNamespace(
            scalars=AsyncMock(return_value=SimpleNamespace(
                all=lambda: [corrupt, good, legacy_null],
            )),
        )
        results = await service.calendar(session, "era")
        self.assertEqual([row["id"] for row in results], [43, 44])
        self.assertEqual(results[0]["revision"], 2)
        session.scalars.assert_awaited_once()


class MalformedCalendarMetadataWriteTests(unittest.IsolatedAsyncioTestCase):
    async def test_edit_rejects_non_object_without_mutating_or_flushing(self):
        for malformed in ([], ["x"], "legacy", 7, True):
            with self.subTest(metadata=malformed):
                item = _item(malformed)
                session = SimpleNamespace(scalar=AsyncMock(return_value=item), flush=AsyncMock())
                user = SimpleNamespace(id=7)
                with patch.object(service, "require_access", new_callable=AsyncMock):
                    with self.assertRaisesRegex(ValueError, "повреждены"):
                        await service.update_entry(
                            session, user, object(), "era", item.id, {"title": "Новое"}, 0,
                        )
                self.assertEqual(item.title, "Материал")
                self.assertEqual(item.metadata_json, malformed)
                session.flush.assert_not_awaited()

    async def test_idempotency_collision_with_corrupt_json_fails_closed(self):
        item = _item(["invalid", "legacy"])
        session = SimpleNamespace(scalar=AsyncMock(return_value=item), flush=AsyncMock())
        user = SimpleNamespace(id=7)
        with (
            patch.object(service, "require_access", new_callable=AsyncMock),
            patch.object(service, "_validate_responsible", new_callable=AsyncMock),
        ):
            with self.assertRaisesRegex(ValueError, "Ключ запроса"):
                await service.create_entry(
                    session, user, object(), "era",
                    {"title": "Материал", "platform": "telegram"}, "same-key",
                )
        self.assertEqual(item.metadata_json, ["invalid", "legacy"])
        session.flush.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
