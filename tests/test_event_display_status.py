"""Participant event badges must reflect real lifecycle states."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.api.v1.events import _display_status
from app.utils.constants import EventStatus, RegistrationStatus


class EventDisplayStatusTests(unittest.TestCase):
    def test_active_event_is_happening_now(self) -> None:
        event = SimpleNamespace(status=EventStatus.ACTIVE)
        self.assertEqual(_display_status(event, None, remaining=0), "Идёт сейчас")

    def test_draft_is_preparing_not_vague_soon(self) -> None:
        event = SimpleNamespace(status=EventStatus.DRAFT)
        self.assertEqual(_display_status(event, None, remaining=None), "Готовится")

    def test_registered_overrides_active(self) -> None:
        event = SimpleNamespace(status=EventStatus.ACTIVE)
        registration = SimpleNamespace(status=RegistrationStatus.REGISTERED)
        self.assertEqual(_display_status(event, registration, remaining=None), "Вы зарегистрированы")

    def test_open_event_without_registration_requirement(self) -> None:
        event = SimpleNamespace(status=EventStatus.PUBLISHED)
        self.assertEqual(
            _display_status(event, None, remaining=None, registration_required=False),
            "Без регистрации",
        )
        self.assertEqual(
            _display_status(event, None, remaining=None, registration_required=True),
            "Регистрация открыта",
        )

    def test_deadline_closure_is_not_shown_as_open(self) -> None:
        """Published event past registration_close_at must not say «открыта»."""
        event = SimpleNamespace(status=EventStatus.PUBLISHED)
        self.assertEqual(
            _display_status(
                event,
                None,
                remaining=5,
                registration_required=True,
                registration_closed=True,
            ),
            "Регистрация закрыта",
        )
        # No-registration events stay «Без регистрации» even after a stale deadline.
        self.assertEqual(
            _display_status(
                event,
                None,
                remaining=None,
                registration_required=False,
                registration_closed=True,
            ),
            "Без регистрации",
        )


if __name__ == "__main__":
    unittest.main()
