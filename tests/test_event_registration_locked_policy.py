"""Registration policy is authoritative only after locking its database rows.

Mocked database operations; no Telegram sends, live registrations or points.
A real PostgreSQL concurrent-admin race test remains a release prerequisite.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.event_service import register_for_event
from app.utils.constants import EventStatus, RegistrationStatus


def _event(status=EventStatus.REGISTRATION_OPEN):
    return SimpleNamespace(id=42, status=status, participant_limit=1)


def _policy(*, required=True, waitlist=False, closed=False):
    return SimpleNamespace(
        registration_required=required,
        waitlist_enabled=waitlist,
        registration_close_at=(
            datetime.now(timezone.utc) - timedelta(minutes=1) if closed else None
        ),
    )


def _session(*rows):
    return SimpleNamespace(
        scalar=AsyncMock(side_effect=list(rows)),
        flush=AsyncMock(),
        add=MagicMock(),
    )


class LockedEventRegistrationPolicyTests(IsolatedAsyncioTestCase):
    async def test_closed_event_after_lock_rejects_stale_open_event(self):
        stale = _event()
        session = _session(_event(EventStatus.REGISTRATION_CLOSED))
        with patch("app.services.event_service.audit", new_callable=AsyncMock) as audit:
            registration, error = await register_for_event(session, stale, 17)
        self.assertIsNone(registration)
        self.assertEqual(error, "closed")
        self.assertEqual(session.scalar.await_count, 1)
        audit.assert_not_awaited()

    async def test_newly_closed_deadline_rejects_stale_caller(self):
        session = _session(_event(), _policy(closed=True))
        with patch(
            "app.services.event_service.award_event_registration",
            new_callable=AsyncMock,
        ) as award:
            registration, error = await register_for_event(
                session, _event(), 17, waitlist_enabled=True
            )
        self.assertIsNone(registration)
        self.assertEqual(error, "closed")
        award.assert_not_awaited()

    async def test_registration_disabled_under_lock_never_awards(self):
        session = _session(_event(), _policy(required=False))
        with patch(
            "app.services.event_service.award_event_registration",
            new_callable=AsyncMock,
        ) as award:
            registration, error = await register_for_event(session, _event(), 17)
        self.assertIsNone(registration)
        self.assertEqual(error, "registration_not_required")
        award.assert_not_awaited()

    async def test_stale_true_waitlist_flag_cannot_override_disabled_policy(self):
        session = _session(_event(), _policy(waitlist=False), None)
        with patch(
            "app.services.event_service.available_places",
            new_callable=AsyncMock, return_value="0",
        ), patch(
            "app.services.event_service.award_event_registration",
            new_callable=AsyncMock,
        ) as award:
            registration, error = await register_for_event(
                session, _event(), 17, waitlist_enabled=True
            )
        self.assertIsNone(registration)
        self.assertEqual(error, "full")
        award.assert_not_awaited()

    async def test_locked_waitlist_policy_overrides_stale_false_caller_flag(self):
        session = _session(_event(), _policy(waitlist=True), None)
        with patch(
            "app.services.event_service.available_places",
            new_callable=AsyncMock, return_value="0",
        ), patch(
            "app.services.event_service.audit",
            new_callable=AsyncMock,
        ) as audit, patch(
            "app.services.event_service.award_event_registration",
            new_callable=AsyncMock,
        ) as award:
            registration, error = await register_for_event(
                session, _event(), 17, waitlist_enabled=False
            )
        self.assertIsNone(error)
        self.assertEqual(registration.status, RegistrationStatus.WAITLIST)
        audit.assert_awaited_once()
        award.assert_awaited_once()
        self.assertEqual(session.scalar.await_count, 3)
        # Both ORM reads are locked and refresh cached pre-lock entities.
        for index in (0, 1):
            statement = session.scalar.await_args_list[index].args[0]
            self.assertIsNotNone(statement._for_update_arg)
            self.assertTrue(statement._execution_options.get("populate_existing"))

    async def test_legacy_event_cannot_waitlist_without_policy_row(self):
        session = _session(_event(), None, None)
        with patch(
            "app.services.event_service.available_places",
            new_callable=AsyncMock, return_value="0",
        ), patch(
            "app.services.event_service.award_event_registration",
            new_callable=AsyncMock,
        ) as award:
            registration, error = await register_for_event(
                session, _event(), 17, waitlist_enabled=True
            )
        self.assertIsNone(registration)
        self.assertEqual(error, "full")
        award.assert_not_awaited()
