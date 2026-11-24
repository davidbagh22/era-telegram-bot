"""Media application must serialize concurrent writes on the real User row."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy.dialects import postgresql

from app.services.media_service import apply_for_media
from app.utils.constants import ApplicationStatus


class MediaApplicationLockTests(IsolatedAsyncioTestCase):
    async def test_application_locks_user_before_membership_lookup(self) -> None:
        user = SimpleNamespace(id=17)
        locked = SimpleNamespace(
            id=17, is_blocked=False, is_archived=False,
            application_status=ApplicationStatus.APPROVED,
        )
        session = SimpleNamespace(
            scalar=AsyncMock(side_effect=[locked, None]),
            add=Mock(),
            flush=AsyncMock(),
        )
        direction = SimpleNamespace(id=9)
        with patch(
            "app.services.media_service._media_direction",
            new_callable=AsyncMock,
            return_value=direction,
        ) as lookup:
            status = await apply_for_media(session, user)
        self.assertEqual(status, "pending")
        self.assertEqual(session.scalar.await_count, 2)
        lock_query = session.scalar.await_args_list[0].args[0]
        self.assertIn(
            "FOR UPDATE", str(lock_query.compile(dialect=postgresql.dialect()))
        )
        self.assertTrue(lock_query.get_execution_options().get("populate_existing"))
        lookup.assert_awaited_once()
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_revoked_applicant_is_rejected_after_row_lock(self) -> None:
        user = SimpleNamespace(id=17)
        locked = SimpleNamespace(
            id=17, is_blocked=True, is_archived=False,
            application_status=ApplicationStatus.APPROVED,
        )
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=locked),
            add=Mock(),
            flush=AsyncMock(),
        )
        with patch(
            "app.services.media_service._media_direction",
            new_callable=AsyncMock,
        ) as lookup:
            with self.assertRaisesRegex(ValueError, "media_apply_forbidden"):
                await apply_for_media(session, user)
        lookup.assert_not_awaited()
        session.add.assert_not_called()
        session.flush.assert_not_awaited()

    async def test_missing_user_is_rejected_without_creating_membership(self) -> None:
        session = SimpleNamespace(
            scalar=AsyncMock(return_value=None),
            add=Mock(),
            flush=AsyncMock(),
        )
        with self.assertRaisesRegex(ValueError, "media_apply_forbidden"):
            await apply_for_media(session, SimpleNamespace(id=999))
        session.add.assert_not_called()
        session.flush.assert_not_awaited()
