import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


PHONE_RE = re.compile(r"^\+?[0-9()\-\s]{7,20}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def parse_age(value: str) -> int | None:
    try:
        age = int(value.strip())
    except ValueError:
        return None
    return age if 14 <= age <= 100 else None


def normalize_phone(value: str) -> str | None:
    value = value.strip()
    if not PHONE_RE.fullmatch(value):
        return None
    digits = re.sub(r"\D", "", value)
    return f"+{digits}" if value.startswith("+") else digits


def normalize_email(value: str) -> str | None:
    value = value.strip().casefold()
    return value if len(value) <= 255 and EMAIL_RE.fullmatch(value) else None


def parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def parse_time(value: str) -> time | None:
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError:
        return None


def parse_deadline(value: str, timezone: str = "Asia/Yerevan") -> datetime | None:
    raw = " ".join((value or "").strip().lower().split())
    if not raw:
        return None

    tz = ZoneInfo(timezone or "Asia/Yerevan")
    now = datetime.now(tz)

    relative = re.fullmatch(r"(сегодня|завтра)\s+(\d{1,2}:\d{2})", raw)
    if relative:
        day_word, raw_time = relative.groups()
        parsed_time = parse_time(raw_time)
        if not parsed_time:
            return None
        target_date = now.date() + (timedelta(days=1) if day_word == "завтра" else timedelta())
        candidate = datetime.combine(target_date, parsed_time, tzinfo=tz)
        return candidate if candidate > now else None

    parsed_time = parse_time(raw)
    if parsed_time:
        candidate = datetime.combine(now.date(), parsed_time, tzinfo=tz)
        return candidate if candidate > now else candidate + timedelta(days=1)

    normalized = raw.replace("/", ".").replace("-", ".")
    patterns = (
        (r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}:\d{2})$", True, True),
        (r"^(\d{1,2})\.(\d{1,2})\s+(\d{1,2}:\d{2})$", False, True),
        (r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", True, False),
        (r"^(\d{1,2})\.(\d{1,2})$", False, False),
    )
    for pattern, has_year, has_time in patterns:
        match = re.fullmatch(pattern, normalized)
        if not match:
            continue
        parts = match.groups()
        day = int(parts[0])
        month = int(parts[1])
        if has_year and has_time:
            year = int(parts[2])
            raw_time = parts[3]
        elif has_year:
            year = int(parts[2])
            raw_time = "23:59"
        elif has_time:
            year = now.year
            raw_time = parts[2]
        else:
            year = now.year
            raw_time = "23:59"
        parsed_time = parse_time(raw_time)
        if not parsed_time:
            return None
        try:
            candidate = datetime.combine(date(year, month, day), parsed_time, tzinfo=tz)
        except ValueError:
            return None
        if not has_year and candidate <= now:
            try:
                candidate = datetime.combine(date(year + 1, month, day), parsed_time, tzinfo=tz)
            except ValueError:
                return None
        return candidate if candidate > now else None

    return None


def clean_text(value: str, max_length: int = 2000) -> str | None:
    value = " ".join(value.split()).strip()
    return value[:max_length] if value else None
