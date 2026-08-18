from datetime import datetime, timezone

from app.services.referral_service import _month_bounds


def test_referral_monthly_cap_uses_yerevan_calendar_boundaries() -> None:
    start, end = _month_bounds(datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc))

    assert start == datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 31, 20, 0, tzinfo=timezone.utc)
