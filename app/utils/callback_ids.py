"""Parse numeric IDs from untrusted Telegram callback data safely."""

PG_INTEGER_MAX = 2_147_483_647


def positive_pg_int_callback(data: str | None, prefix: str) -> int | None:
    """Accept only positive ASCII PostgreSQL INTEGER IDs after an exact prefix."""
    if not isinstance(data, str) or not data.startswith(prefix):
        return None
    raw = data[len(prefix):]
    if not 1 <= len(raw) <= 10 or not raw.isascii() or not raw.isdecimal():
        return None
    number = int(raw)
    return number if 0 < number <= PG_INTEGER_MAX else None


def positive_pg_int_value(value: object) -> int | None:
    """Validate a numeric ID recovered from FSM state (int or ASCII string)."""
    if type(value) is int:
        return value if 0 < value <= PG_INTEGER_MAX else None
    if isinstance(value, str):
        return positive_pg_int_callback(value, "")
    return None
