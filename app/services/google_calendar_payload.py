"""Pure, side-effect-free Google Calendar payload builder for ERA events.

This module does not authenticate, send invitations, or write calendar entries.
The caller must supply an explicit end time; event records have no duration.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

ERA_TIMEZONE = "Asia/Yerevan"


def build_calendar_payload(event, *, end_time: time) -> dict:
    """Build a Google Calendar events.insert/update body without attendees.

    Raises ValueError for missing/invalid times; never guesses a duration.
    """
    if not event.title or not event.title.strip():
        raise ValueError("Event title is required")
    start = datetime.combine(event.event_date, event.event_time, ZoneInfo(ERA_TIMEZONE))
    end = datetime.combine(event.event_date, end_time, ZoneInfo(ERA_TIMEZONE))
    if end <= start:
        raise ValueError("End time must be later than start time on the same date")
    return {
        "summary": event.title.strip(),
        "description": event.description or "",
        "location": event.location or "",
        "start": {"dateTime": start.isoformat(), "timeZone": ERA_TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": ERA_TIMEZONE},
        "extendedProperties": {"private": {"era_event_id": str(event.id)}},
    }
