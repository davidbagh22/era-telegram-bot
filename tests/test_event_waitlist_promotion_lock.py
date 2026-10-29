"""Waitlist promotion must serialize its capacity check with registration.

Mocked database interactions only. PostgreSQL two-session race tests remain
a release prerequisite; SQLite cannot prove row-lock semantics.
"""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.services.event_service import promote_waitlist
from app.utils.constants import RegistrationStatus


def _event(limit=1):
    return SimpleNamespace(id=42, participant_limit=limit)


class _NoAutoflushGuard:
    def __init__(self):
        self.entries = 0
        self.active = False

    def __enter__(self):
        self.entries += 1
        self.active = True

    def __exit__(self, *args):
        self.active = False


def _session(*rows):
    return SimpleNamespace(
        scalar=AsyncMock(side_effect=list(rows)),
        flush=AsyncMock(),
        no_autoflush=_NoAutoflushGuard(),
    )


class WaitlistPromotionLockTests(IsolatedAsyncioTestCase):
    async def test_event_disappeared_under_lock_does_not_promote(self):
        session = _session(None)
        with patch(
            "app.services.event_service.available_places",
            new_callable=AsyncMock,
        ) as places:
            result = await promote_waitlist(session, _event())
        self.assertIsNone(result)
        places.assert_not_awaited()

    async def test_stale_limit_is_rechecked_under_event_lock(self):
        session = _session(_event(limit=None))
        with patch(
            "app.services.event_service.available_places",
            new_callable=AsyncMock,
        ) as places:
            result = await promote_waitlist(session, _event(limit=1))
        self.assertIsNone(result)
        places.assert_not_awaited()

    async def test_no_capacity_after_lock_prevents_overpromotion(self):
        session = _session(_event())
        with patch(
            "app.services.event_service.available_places",
            new_callable=AsyncMock, return_value="0",
        ) as places, patch(
            "app.services.event_service.audit",
            new_callable=AsyncMock,
        ) as audit:
            result = await promote_waitlist(session, _event())
        self.assertIsNone(result)
        places.assert_awaited_once()
        audit.assert_not_awaited()
        self.assertEqual(session.scalar.await_count, 1)

    async def test_promotion_checks_locked_event_before_locking_waiter(self):
        waiting = SimpleNamespace(
            user_id=17, status=RegistrationStatus.WAITLIST
        )
        session = _session(_event(), waiting)
        with patch(
            "app.services.event_service.available_places",
            new_callable=AsyncMock, return_value="1",
        ), patch(
            "app.services.event_service.audit",
            new_callable=AsyncMock,
        ) as audit:
            result = await promote_waitlist(session, _event())
        self.assertIs(result, waiting)
        self.assertEqual(waiting.status, RegistrationStatus.REGISTERED)
        session.flush.assert_awaited_once()
        audit.assert_awaited_once()
        self.assertEqual(session.scalar.await_count, 2)
        event_query = session.scalar.await_args_list[0].args[0]
        waiter_query = session.scalar.await_args_list[1].args[0]
        self.assertIsNotNone(event_query._for_update_arg)
        self.assertTrue(event_query._execution_options.get("populate_existing"))
        self.assertIsNotNone(waiter_query._for_update_arg)
        self.assertEqual(session.no_autoflush.entries, 1)
        self.assertFalse(session.no_autoflush.active)
