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


    async def test_calendar_rechecks_explicit_null_and_invalid_media_area(self):
        # SQL JSON extraction can coalesce JSON null to ERA. Always recheck
        # each returned record before exposing its title or body.
        valid_era = _item({"media_area": "era"})
        valid_era.id = 51
        legacy_missing = _item({"workspace_revision": 0})
        legacy_missing.id = 52
        legacy_sql_null = _item(None)
        legacy_sql_null.id = 53
        explicit_null = _item({"media_area": None})
        explicit_null.id = 54
        invalid_area = _item({"media_area": ["era"]})
        invalid_area.id = 55
        wrong_area = _item({"media_area": "ksoors"})
        wrong_area.id = 56
        session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(
            all=lambda: [valid_era, legacy_missing, legacy_sql_null,
                         explicit_null, invalid_area, wrong_area],
        )))
        result = await service.calendar(session, "era")
        self.assertEqual([row["id"] for row in result], [51, 52, 53])
        self.assertTrue(all(row["area"] == "era" for row in result))
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


class CalendarSqlPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_json_cannot_exhaust_page_before_valid_rows(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from app.database.base import Base
        from app.database.media_models import MediaContentItem

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                metadata = [
                    {"media_area": "era"},
                    {"workspace_revision": 0},  # historical missing area => ERA
                    {"media_area": "ksoors"},
                    None,  # JSON literal null; schema column is NOT NULL
                    {"media_area": None},  # explicit JSON null must not leak
                ]
                metadata.extend([["invalid"]] * 125)
                session.add_all([
                    MediaContentItem(source_kind="media_workspace", source_key=f"page-{i}",
                                     kind="text", title=f"item-{i}", status="planned",
                                     metadata_json=value)
                    for i, value in enumerate(metadata)
                ])
                await session.commit()
            async with factory() as session:
                era = await service.calendar(session, "era")
                self.assertEqual([row["id"] for row in era], [2, 1])
                self.assertTrue(all(row["area"] == "era" for row in era))
                self.assertEqual([row["id"] for row in
                                  await service.calendar(session, "era", before_id=2)], [1])
                ksoors = await service.calendar(session, "ksoors")
                self.assertEqual([row["id"] for row in ksoors], [3])
                self.assertTrue(all(row["area"] == "ksoors" for row in ksoors))
        finally:
            await engine.dispose()

    async def test_json_type_filter_is_postgresql_compatible_by_compilation(self):
        from sqlalchemy import select
        from sqlalchemy.dialects import postgresql
        from app.database.media_models import MediaContentItem

        query = select(MediaContentItem.id).where(service._calendar_metadata_filter("postgresql"))
        compiled = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        self.assertIn("json_typeof", compiled)
        self.assertIn("->", compiled)
        with self.assertRaisesRegex(RuntimeError, "Unsupported"):
            service._calendar_metadata_filter("unknown")


if __name__ == "__main__":
    unittest.main()
