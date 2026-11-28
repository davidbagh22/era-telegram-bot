from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace

import pytest

from app.api.v1 import event_attendance as api_mod
from app.services.event_attendance_service import ParticipantAttendanceState
from app.utils.constants import EventStatus


def _state(
    *,
    event_date: date,
    status: EventStatus = EventStatus.REGISTRATION_OPEN,
    eligible: bool = True,
    confirmed: bool = False,
    confirmation_open: bool = False,
    confirmation_closed: bool = False,
) -> ParticipantAttendanceState:
    event = SimpleNamespace(
        id=42,
        event_date=event_date,
        event_time=time(18, 0),
        status=status,
        points_for_visit=20,
    )
    return ParticipantAttendanceState(
        event=event,
        eligible=eligible,
        confirmation_open=confirmation_open,
        confirmation_closed=confirmation_closed,
        confirmed=confirmed,
        points_awarded=False,
    )


def test_future_event_cannot_submit_proof_in_yerevan_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_mod, "_yerevan_today", lambda: date(2026, 11, 28))
    out = api_mod._state_out(_state(event_date=date(2026, 12, 19)))
    assert out.can_submit_proof is False


def test_event_day_allows_proof_for_registered_participant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_mod, "_yerevan_today", lambda: date(2026, 11, 28))
    out = api_mod._state_out(_state(event_date=date(2026, 11, 28)))
    assert out.can_submit_proof is True


def test_active_event_allows_proof_even_if_started_early(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_mod, "_yerevan_today", lambda: date(2026, 11, 28))
    out = api_mod._state_out(
        _state(event_date=date(2026, 11, 29), status=EventStatus.ACTIVE),
    )
    assert out.can_submit_proof is True


def test_cancelled_or_closed_event_disables_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_mod, "_yerevan_today", lambda: date(2026, 11, 28))

    cancelled = api_mod._state_out(
        _state(event_date=date(2026, 11, 28), status=EventStatus.CANCELLED),
    )
    assert cancelled.can_submit_proof is False

    closed = api_mod._state_out(
        _state(
            event_date=date(2026, 11, 27),
            status=EventStatus.COMPLETED,
            confirmation_closed=True,
        ),
    )
    assert closed.can_submit_proof is False
