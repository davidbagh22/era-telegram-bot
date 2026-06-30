import re
from datetime import date, datetime, time


PHONE_RE = re.compile(r"^\+?[0-9()\-\s]{7,20}$")


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


def clean_text(value: str, max_length: int = 2000) -> str | None:
    value = " ".join(value.split()).strip()
    return value[:max_length] if value else None
