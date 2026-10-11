"""Regression tests for the approved daily reading cadence."""
from datetime import date, timedelta

from app.services.book_club_service import publication_number
from app.handlers.book_club import AUDIOBOOK_URL, READ_BOOK_URL, issue_keyboard


def test_daily_releases_for_48_days():
    start = date(2026, 10, 10)
    for offset in range(48):
        assert publication_number(start + timedelta(days=offset)) == offset + 1
    assert publication_number(start - timedelta(days=1)) is None
    assert publication_number(start + timedelta(days=48)) is None


def test_book_and_audio_links_for_every_issue():
    for number in (1, 16, 17, 32, 33, 48):
        keyboard = issue_keyboard(number)
        links = [button.url for row in keyboard.inline_keyboard for button in row if button.url]
        assert AUDIOBOOK_URL in links
        assert READ_BOOK_URL in links
