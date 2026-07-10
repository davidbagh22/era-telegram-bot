from datetime import date

from app.utils.validators import calculate_age, parse_birth_date


def test_parse_birth_date_requires_dd_mm_yyyy() -> None:
    today = date(2026, 7, 10)

    parsed = parse_birth_date("05.09.2001", today=today)

    assert parsed == date(2001, 9, 5)
    assert calculate_age(parsed, today=today) == 24


def test_parse_birth_date_rejects_invalid_or_out_of_range_values() -> None:
    today = date(2026, 7, 10)

    assert parse_birth_date("2001-09-05", today=today) is None
    assert parse_birth_date("31.02.2001", today=today) is None
    assert parse_birth_date("10.07.2020", today=today) is None
    assert parse_birth_date("10.07.1900", today=today) is None
