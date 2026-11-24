"""Open / activity tasks can be published without a hard deadline."""
from __future__ import annotations

from app.handlers.leader.open_tasks import _day_keyboard
from app.handlers.leader.task_deadline_buttons import _deadline_day_keyboard


def test_open_task_deadline_keyboard_offers_no_deadline_first() -> None:
    rows = _day_keyboard().inline_keyboard
    assert rows[0][0].text == "♾ Без срока"
    assert rows[0][0].callback_data == "opentask:deadline:none"


def test_assigned_task_deadline_keyboard_offers_no_deadline_first() -> None:
    rows = _deadline_day_keyboard().inline_keyboard
    assert rows[0][0].text == "♾ Без срока"
    assert rows[0][0].callback_data == "task:deadline:none"
