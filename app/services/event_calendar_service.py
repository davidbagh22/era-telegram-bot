"""One timezone-aware iCalendar representation for native bot and Mini App."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.database.models import Event
from app.utils.constants import EventStatus


def _text(value: str | None) -> str:
    return (value or "").replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _fold(line: str) -> str:
    # RFC 5545: 75 octets, including the continuation space; never split UTF-8.
    parts, current = [], ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            parts.append(current)
            current = " "
        current += char
    return "\r\n".join([*parts, current])


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_event_calendar(event: Event, experience=None, *, timezone_name="Asia/Yerevan") -> bytes:
    tz = ZoneInfo(timezone_name)
    start = datetime.combine(event.event_date, event.event_time, tzinfo=tz)
    end_time = experience.end_time if experience else None
    end = datetime.combine(event.event_date, end_time, tzinfo=tz) if end_time else None
    if end is not None and end <= start:
        end += timedelta(days=1)
    # Unknown duration is omitted, never misrepresented as a zero-length slot.
    modified = [getattr(event, "created_at", None), getattr(event, "updated_at", None),
                getattr(experience, "updated_at", None)]
    modified = [v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
                for v in modified if v is not None]
    stamp = max(modified) if modified else datetime(2026, 1, 1, tzinfo=timezone.utc)
    description = (experience.full_description if experience else None) or event.description
    location = ", ".join(filter(None, [event.location, experience.address if experience else None]))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ERA//Events//RU", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "BEGIN:VEVENT", f"UID:era-event-{event.id}",
             f"DTSTAMP:{_utc(stamp)}", f"LAST-MODIFIED:{_utc(stamp)}",
             f"SEQUENCE:{int(stamp.timestamp())}", f"DTSTART:{_utc(start)}"]
    if end:
        lines.append(f"DTEND:{_utc(end)}")
    lines.extend([f"SUMMARY:{_text(event.title)}", f"DESCRIPTION:{_text(description)}",
                  f"LOCATION:{_text(location)}", f"X-ERA-TIMEZONE:{_text(timezone_name)}",
                  "STATUS:CANCELLED" if event.status == EventStatus.CANCELLED else "STATUS:CONFIRMED",
                  "END:VEVENT", "END:VCALENDAR"])
    return ("\r\n".join(_fold(line) for line in lines) + "\r\n").encode("utf-8")
