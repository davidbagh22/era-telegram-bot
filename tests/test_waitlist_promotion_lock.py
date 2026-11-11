"""Waitlist promotions must serialize on the event row before checking seats."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.event_service import promote_waitlist


class WaitlistPromotionLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_deleted_event_is_never_promoted(self):
        session = SimpleNamespace(scalar=AsyncMock(return_value=None))
        event = SimpleNamespace(id=47, participant_limit=1)
        with patch("app.services.event_service.available_places", new_callable=AsyncMock) as places:
            result = await promote_waitlist(session, event)
        self.assertIsNone(result)
        session.scalar.assert_awaited_once()
        query = session.scalar.await_args.args[0]
        self.assertIn("FOR UPDATE", str(query.compile()))
        self.assertTrue(query.get_execution_options()["populate_existing"])
        self.assertFalse(query.get_execution_options()["autoflush"])
        places.assert_not_awaited()

    async def test_full_capacity_rechecked_after_event_lock(self):
        event = SimpleNamespace(id=48, participant_limit=1)
        session = SimpleNamespace(scalar=AsyncMock(return_value=event))
        with patch("app.services.event_service.available_places", new=AsyncMock(return_value=0)) as places:
            result = await promote_waitlist(session, event)
        self.assertIsNone(result)
        session.scalar.assert_awaited_once()
        places.assert_awaited_once_with(session, event)
