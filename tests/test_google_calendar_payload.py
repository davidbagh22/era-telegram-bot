from datetime import date, time
from types import SimpleNamespace

import pytest

from app.services.google_calendar_payload import build_calendar_payload


def event(**overrides):
    fields = dict(id=42, title="  Встреча ЭРА  ", description="Описание",
                  location="Ереван", event_date=date(2026, 12, 12),
                  event_time=time(13, 0))
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_calendar_payload_preserves_yerevan_time_and_identity():
    body = build_calendar_payload(event(), end_time=time(14, 30))
    assert body["summary"] == "Встреча ЭРА"
    assert body["start"] == {"dateTime": "2026-12-12T13:00:00+04:00", "timeZone": "Asia/Yerevan"}
    assert body["end"]["dateTime"] == "2026-12-12T14:30:00+04:00"
    assert body["extendedProperties"]["private"]["era_event_id"] == "42"
    assert body["location"] == "Ереван"
    assert "attendees" not in body
    assert "sendUpdates" not in body


@pytest.mark.parametrize("end_time", [time(13, 0), time(12, 59)])
def test_rejects_nonpositive_duration(end_time):
    with pytest.raises(ValueError, match="End time"):
        build_calendar_payload(event(), end_time=end_time)


def test_rejects_blank_title():
    with pytest.raises(ValueError, match="title"):
        build_calendar_payload(event(title="  "), end_time=time(14, 0))


def test_optional_fields_are_safe():
    body = build_calendar_payload(event(description=None, location=None), end_time=time(14, 0))
    assert body["description"] == ""
    assert body["location"] == ""


@pytest.mark.parametrize("invalid_id", [None, 0, -1, "", "42", True])
def test_rejects_unpersisted_or_ambiguous_event_id(invalid_id):
    with pytest.raises(ValueError, match="persisted positive ERA event ID"):
        build_calendar_payload(event(id=invalid_id), end_time=time(14, 0))
