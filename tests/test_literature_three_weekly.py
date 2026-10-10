"""Regression tests for the approved three-day reading cadence."""
from datetime import date

from app.services.book_club_service import publication_number
from app.handlers.book_club import AUDIOBOOK_URL, issue_keyboard


def test_three_weekly_releases_and_no_weekend_delivery():
    assert publication_number(date(2026, 10, 10)) == 1
    assert publication_number(date(2026, 10, 11)) is None
    assert publication_number(date(2026, 10, 12)) == 2
    assert publication_number(date(2026, 10, 13)) is None
    assert publication_number(date(2026, 10, 14)) == 3
    assert publication_number(date(2026, 10, 16)) == 4
    assert publication_number(date(2026, 10, 19)) == 5
    assert publication_number(date(2026, 10, 17)) is None


def test_last_issue_and_program_end():
    assert publication_number(date(2027, 1, 27)) == 48
    assert publication_number(date(2027, 1, 29)) is None
    assert publication_number(date(2027, 2, 1)) is None


def test_audiobook_link_for_every_issue():
    for number in (1, 16, 17, 32, 33, 48):
        keyboard = issue_keyboard(number)
        links = [button.url for row in keyboard.inline_keyboard for button in row if button.url]
        assert AUDIOBOOK_URL in links
