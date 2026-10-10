"""Regression tests for the approved three-day reading cadence."""
from datetime import date

from app.services.book_club_service import publication_number
from app.handlers.book_club import AUDIOBOOK_PARTS, issue_keyboard


def test_three_weekly_releases_and_no_weekend_delivery():
    assert publication_number(date(2026, 10, 11)) is None
    assert publication_number(date(2026, 10, 12)) == 1
    assert publication_number(date(2026, 10, 13)) is None
    assert publication_number(date(2026, 10, 14)) == 2
    assert publication_number(date(2026, 10, 16)) == 3
    assert publication_number(date(2026, 10, 19)) == 4
    assert publication_number(date(2026, 10, 17)) is None


def test_last_issue_and_program_end():
    assert publication_number(date(2027, 1, 29)) == 48
    assert publication_number(date(2027, 2, 1)) is None


def test_audiobook_link_per_volume():
    for number, expected_part in ((1, 0), (16, 0), (17, 1), (32, 1), (33, 2), (48, 2)):
        keyboard = issue_keyboard(number)
        links = [button.url for row in keyboard.inline_keyboard for button in row if button.url]
        assert AUDIOBOOK_PARTS[expected_part] in links
