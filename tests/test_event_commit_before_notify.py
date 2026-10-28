"""Regression: never send registration/waitlist Telegram notices before DB commit.

These unit tests mock the Telegram boundary; no real users or messages are touched.
The immediate post-commit send is still non-durable (issue #497).
"""
from __future__ import annotations

import unittest
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.v1.events import cancel_event_registration, register_event
from app.handlers.participant.events_stability_block8 import event_join
from app.utils.constants import EventStatus, RegistrationStatus


def _event():
    return SimpleNamespace(
        id=42,
        title="Test event",
        event_date=date(2026, 11, 5),
        event_time=time(18, 0),
        location="Test",
        status=EventStatus.REGISTRATION_OPEN,
    )


class EventCommitBeforeNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_registration_commits_before_confirmation(self):
        order = []
        event = _event()
        registration = SimpleNamespace(status=RegistrationStatus.REGISTERED)
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[event, None]),
            commit=AsyncMock(side_effect=lambda: order.append("commit")),
        )
        user = SimpleNamespace(id=9, telegram_id=12345)
        confirmation = AsyncMock(side_effect=lambda *args: order.append("send"))
        with (
            patch("app.api.v1.events.register_for_event", new=AsyncMock(return_value=(registration, None))),
            patch("app.api.v1.events._to_event_out", new=AsyncMock(return_value="result")),
            patch("app.api.v1.events._send_registration_confirmation", new=confirmation),
        ):
            result = await register_event(42, user=user, session=session, bot=object(), settings=object())
        self.assertEqual(result, "result")
        self.assertEqual(order, ["commit", "send"])
        session.commit.assert_awaited_once()
        confirmation.assert_awaited_once()

    async def test_registration_commit_failure_does_not_send(self):
        event = _event()
        registration = SimpleNamespace(status=RegistrationStatus.REGISTERED)
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[event, None]),
            commit=AsyncMock(side_effect=RuntimeError("commit failed")),
        )
        confirmation = AsyncMock()
        with (
            patch("app.api.v1.events.register_for_event", new=AsyncMock(return_value=(registration, None))),
            patch("app.api.v1.events._to_event_out", new=AsyncMock(return_value="result")),
            patch("app.api.v1.events._send_registration_confirmation", new=confirmation),
        ):
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                await register_event(42, user=SimpleNamespace(id=9), session=session,
                                     bot=object(), settings=object())
        confirmation.assert_not_awaited()

    async def test_waitlist_promotion_commits_before_notice(self):
        order = []
        event = _event()
        registration = SimpleNamespace(status=RegistrationStatus.REGISTERED)
        promoted = SimpleNamespace(user_id=11)
        promoted_user = SimpleNamespace(telegram_id=777)
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[event, promoted_user, None]),
            commit=AsyncMock(side_effect=lambda: order.append("commit")),
        )
        notification = AsyncMock(side_effect=lambda *args, **kwargs: order.append("send"))
        with (
            patch("app.api.v1.events._get_registration", new=AsyncMock(return_value=registration)),
            patch("app.api.v1.events.promote_waitlist", new=AsyncMock(return_value=promoted)),
            patch("app.api.v1.events._to_event_out", new=AsyncMock(return_value="result")),
            patch("app.api.v1.events.safe_send", new=notification),
            patch("app.api.v1.events._event_keyboard", return_value=None),
        ):
            result = await cancel_event_registration(
                42, user=SimpleNamespace(id=9), session=session,
                bot=object(), settings=object(),
            )
        self.assertEqual(result, "result")
        self.assertEqual(registration.status, RegistrationStatus.NOT_COMING)
        self.assertEqual(order, ["commit", "send"])
        notification.assert_awaited_once()

    async def test_waitlist_promotion_commit_failure_does_not_send(self):
        event = _event()
        registration = SimpleNamespace(status=RegistrationStatus.REGISTERED)
        session = SimpleNamespace(
            get=AsyncMock(side_effect=[event, SimpleNamespace(telegram_id=777), None]),
            commit=AsyncMock(side_effect=RuntimeError("commit failed")),
        )
        notification = AsyncMock()
        with (
            patch("app.api.v1.events._get_registration", new=AsyncMock(return_value=registration)),
            patch("app.api.v1.events.promote_waitlist", new=AsyncMock(return_value=SimpleNamespace(user_id=11))),
            patch("app.api.v1.events._to_event_out", new=AsyncMock(return_value="result")),
            patch("app.api.v1.events.safe_send", new=notification),
        ):
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                await cancel_event_registration(
                    42, user=SimpleNamespace(id=9), session=session,
                    bot=object(), settings=object(),
                )
        notification.assert_not_awaited()


    async def test_native_bot_join_commits_before_success_message(self):
        order = []
        event = _event()
        event.participant_limit = None
        session = SimpleNamespace(
            get=AsyncMock(return_value=event),
            commit=AsyncMock(side_effect=lambda: order.append("commit")),
        )
        message = SimpleNamespace(answer=AsyncMock(side_effect=lambda *args, **kwargs: order.append("send")))
        call = SimpleNamespace(
            data="event:join:42", answer=AsyncMock(), message=message,
        )
        with (
            patch("app.handlers.participant.events_stability_block8._approved", return_value=True),
            patch("app.handlers.participant.events_stability_block8.register_for_event",
                  new=AsyncMock(return_value=(SimpleNamespace(), None))),
            patch("app.handlers.participant.events_stability_block8.registration_stats",
                  new=AsyncMock(return_value={"registered": 1, "free": "без ограничений"})),
        ):
            await event_join(call, user=SimpleNamespace(id=9), session=session)
        self.assertEqual(order, ["commit", "send"])
        session.commit.assert_awaited_once()
        message.answer.assert_awaited_once()

    async def test_native_bot_join_commit_failure_does_not_confirm(self):
        event = _event()
        session = SimpleNamespace(
            get=AsyncMock(return_value=event),
            commit=AsyncMock(side_effect=RuntimeError("commit failed")),
        )
        message = SimpleNamespace(answer=AsyncMock())
        call = SimpleNamespace(
            data="event:join:42", answer=AsyncMock(), message=message,
        )
        with (
            patch("app.handlers.participant.events_stability_block8._approved", return_value=True),
            patch("app.handlers.participant.events_stability_block8.register_for_event",
                  new=AsyncMock(return_value=(SimpleNamespace(), None))),
            patch("app.handlers.participant.events_stability_block8.registration_stats",
                  new=AsyncMock(return_value={"registered": 1, "free": "без ограничений"})),
        ):
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                await event_join(call, user=SimpleNamespace(id=9), session=session)
        message.answer.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
