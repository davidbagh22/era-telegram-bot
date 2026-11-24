"""Waitlist must not award registration digital points before a seat (#513)."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import event_service
from app.utils.constants import EventStatus, RegistrationStatus


class WaitlistRegistrationPointsTests(IsolatedAsyncioTestCase):
    async def test_waitlist_join_skips_digital_award(self):
        event = SimpleNamespace(
            id=11,
            status=EventStatus.PUBLISHED,
            participant_limit=1,
            title="Полный зал",
        )
        experience = SimpleNamespace(
            waitlist_enabled=True,
            registration_required=True,
            registration_close_at=None,
            broadcast_targets=None,
        )
        session = AsyncMock()
        registration = SimpleNamespace(status=RegistrationStatus.WAITLIST, signup=None)

        with (
            patch.object(event_service, "_lock_event_for_capacity", new=AsyncMock(return_value=event)),
            patch.object(event_service.anniversary, "is_public_anniversary", return_value=False),
            patch.object(event_service, "registration_is_closed", return_value=False),
            patch.object(event_service, "available_places", new=AsyncMock(return_value=0)),
            patch.object(event_service, "award_event_registration", new=AsyncMock()) as award,
            patch.object(event_service, "audit", new=AsyncMock()),
        ):
            session.get = AsyncMock(return_value=experience)
            session.scalar = AsyncMock(return_value=None)
            session.add = MagicMock()
            session.flush = AsyncMock()
            result, error = await event_service.register_for_event(session, event, user_id=7)

        self.assertIsNone(error)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, RegistrationStatus.WAITLIST)
        award.assert_not_awaited()

    async def test_confirmed_registration_awards_digital_points(self):
        event = SimpleNamespace(
            id=12,
            status=EventStatus.PUBLISHED,
            participant_limit=10,
            title="Открыто",
        )
        experience = SimpleNamespace(
            waitlist_enabled=True,
            registration_required=True,
            registration_close_at=None,
            broadcast_targets=None,
        )
        session = AsyncMock()
        with (
            patch.object(event_service, "_lock_event_for_capacity", new=AsyncMock(return_value=event)),
            patch.object(event_service.anniversary, "is_public_anniversary", return_value=False),
            patch.object(event_service, "registration_is_closed", return_value=False),
            patch.object(event_service, "available_places", new=AsyncMock(return_value=5)),
            patch.object(event_service, "award_event_registration", new=AsyncMock()) as award,
            patch.object(event_service, "audit", new=AsyncMock()),
        ):
            session.get = AsyncMock(return_value=experience)
            session.scalar = AsyncMock(return_value=None)
            session.add = MagicMock()
            session.flush = AsyncMock()
            result, error = await event_service.register_for_event(session, event, user_id=8)

        self.assertIsNone(error)
        self.assertEqual(result.status, RegistrationStatus.REGISTERED)
        award.assert_awaited_once_with(session, user_id=8, event_id=12)

    async def test_promote_waitlist_awards_digital_points(self):
        event = SimpleNamespace(id=13, participant_limit=2, title="Место")
        waiting = SimpleNamespace(
            user_id=9,
            status=RegistrationStatus.WAITLIST,
            updated_at=None,
        )
        session = AsyncMock()
        with (
            patch.object(event_service, "_lock_event_for_capacity", new=AsyncMock(return_value=event)),
            patch.object(event_service.anniversary, "is_public_anniversary", return_value=False),
            patch.object(event_service, "available_places", new=AsyncMock(return_value=1)),
            patch.object(event_service, "award_event_registration", new=AsyncMock()) as award,
            patch.object(event_service, "audit", new=AsyncMock()),
        ):
            session.scalar = AsyncMock(return_value=waiting)
            session.flush = AsyncMock()
            promoted = await event_service.promote_waitlist(session, event)

        self.assertIs(promoted, waiting)
        self.assertEqual(waiting.status, RegistrationStatus.REGISTERED)
        award.assert_awaited_once_with(session, user_id=9, event_id=13)
