"""Regression checks for native Bot/Mini App registration-policy parity.

All Telegram and database interactions are mocked; no real registration or send.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.handlers.participant.events_stability_block8 import event_join, event_view
from app.services.event_registration_policy import registration_is_closed
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus


def _event(*, limit=1, status=EventStatus.REGISTRATION_OPEN):
    return SimpleNamespace(id=42, status=status, participant_limit=limit)


def _experience(*, required=True, waitlist=False, deadline=None):
    return SimpleNamespace(
        registration_required=required,
        waitlist_enabled=waitlist,
        registration_close_at=deadline,
    )


def _call(action="join"):
    return SimpleNamespace(
        data=f"event:{action}:42",
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )


def _user():
    return SimpleNamespace(
        id=17, application_status=ApplicationStatus.APPROVED,
        is_blocked=False, is_archived=False,
    )


class RegistrationPolicyTests(TestCase):
    def test_legacy_naive_deadline_and_aware_deadline(self):
        now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(registration_is_closed(
            _experience(deadline=datetime(2026, 10, 29, 11, 59)), now=now
        ))
        self.assertFalse(registration_is_closed(
            _experience(deadline=now + timedelta(minutes=1)), now=now
        ))
        self.assertTrue(registration_is_closed(
            _experience(deadline=now), now=now
        ))
        self.assertFalse(registration_is_closed(None, now=now))


class NativeEventRegistrationTests(IsolatedAsyncioTestCase):
    async def test_stale_callback_and_closed_status_never_register(self):
        for event in (None, _event(status=EventStatus.REGISTRATION_CLOSED)):
            call = _call()
            session = SimpleNamespace(get=AsyncMock(return_value=event))
            with patch(
                "app.handlers.participant.events_stability_block8.register_for_event",
                new_callable=AsyncMock,
            ) as register:
                await event_join(call, _user(), session)
                register.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_no_registration_required_and_expired_deadline_reject(self):
        cases = (
            _experience(required=False),
            _experience(deadline=datetime(2020, 1, 1, tzinfo=timezone.utc)),
        )
        for experience in cases:
            call = _call()
            session = SimpleNamespace(get=AsyncMock(side_effect=[_event(), experience]))
            with patch(
                "app.handlers.participant.events_stability_block8.register_for_event",
                new_callable=AsyncMock,
            ) as register:
                await event_join(call, _user(), session)
                register.assert_not_awaited()
                call.message.answer.assert_awaited_once()

    async def test_full_event_waitlist_uses_config_and_confirms_waitlist_not_seat(self):
        call = _call()
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[_event(), _experience(waitlist=True)])
        )
        registration = SimpleNamespace(status=RegistrationStatus.WAITLIST)
        with patch(
            "app.handlers.participant.events_stability_block8.register_for_event",
            new_callable=AsyncMock, return_value=(registration, None),
        ) as register, patch(
            "app.handlers.participant.events_stability_block8.registration_stats",
            new_callable=AsyncMock,
        ) as stats:
            await event_join(call, _user(), session)
            self.assertTrue(register.await_args.kwargs["waitlist_enabled"])
            stats.assert_not_awaited()
            self.assertIn("лист ожидания", call.message.answer.await_args.args[0])

    async def test_old_event_without_experience_does_not_enable_waitlist(self):
        call = _call()
        session = SimpleNamespace(get=AsyncMock(side_effect=[_event(), None]))
        with patch(
            "app.handlers.participant.events_stability_block8.register_for_event",
            new_callable=AsyncMock, return_value=(None, "full"),
        ) as register:
            await event_join(call, _user(), session)
            self.assertFalse(register.await_args.kwargs["waitlist_enabled"])

    async def test_card_offers_waitlist_when_full_and_enabled(self):
        for waitlist, required, should_offer in (
            (True, True, True),
            (False, True, False),
            (True, False, False),
        ):
            call = _call("view")
            session = SimpleNamespace(
                get=AsyncMock(side_effect=[_event(), _experience(
                    required=required, waitlist=waitlist,
                )]),
                scalar=AsyncMock(return_value=0),
            )
            with patch(
                "app.handlers.participant.events_stability_block8.registration_stats",
                new_callable=AsyncMock, return_value={"registered": 1, "free": 0},
            ), patch(
                "app.handlers.participant.events_stability_block8.send_event_card",
                new_callable=AsyncMock,
            ) as card:
                await event_view(call, _user(), session)
                keyboard = card.await_args.kwargs["keyboard"]
                buttons = [button.callback_data for row in keyboard.inline_keyboard for button in row]
                self.assertEqual("event:join:42" in buttons, should_offer)
