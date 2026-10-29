"""Shared registration deadline rule for the Mini App and native ERA bot."""
from datetime import datetime, timezone

from app.database.event_experience import EventExperience


def registration_is_closed(
    experience: EventExperience | None, *, now: datetime | None = None
) -> bool:
    """Treat legacy naive timestamps as UTC, matching the existing Mini App rule."""
    if experience is None or experience.registration_close_at is None:
        return False
    deadline = experience.registration_close_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline <= (now if now is not None else datetime.now(timezone.utc))
