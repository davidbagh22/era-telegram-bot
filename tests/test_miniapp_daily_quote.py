import asyncio
from datetime import datetime, timezone

from app.api.v1 import home
from app.services.daily_public_content_service import text_for_day


def test_miniapp_daily_quote_matches_scheduled_channel_text(monkeypatch) -> None:
    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 10, 21, 12, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(home, "datetime", FixedDateTime)
    result = asyncio.run(home.read_daily_quote(user=None))

    assert result.date == "2026-10-21"
    assert result.text == text_for_day(result.date, "channel_post")
