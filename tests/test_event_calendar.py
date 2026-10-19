from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.events import router
from app.config import Settings
from app.services.event_calendar_service import build_event_calendar
from app.utils.constants import ApplicationStatus, EventStatus


def event(**kwargs):
    return SimpleNamespace(**(dict(id=42, title="Встреча, ЭРА; новая\\тема", description="Первая\nВторая\r\nSTATUS:CANCELLED",
                                  location="Ереван", event_date=date(2026, 10, 24), event_time=time(12, 0),
                                  status=EventStatus.PUBLISHED, created_at=datetime(2026, 10, 19, tzinfo=timezone.utc),
                                  updated_at=datetime(2026, 10, 19, tzinfo=timezone.utc)) | kwargs))


def test_calendar_uses_yerevan_utc_and_escapes_content_without_injection():
    value = build_event_calendar(event()).decode()
    assert "DTSTART:20261024T080000Z\r\n" in value
    assert "DTEND" not in value  # no invented duration
    assert "SUMMARY:Встреча\\, ЭРА\\; новая\\\\тема\r\n" in value
    assert value.count("\r\nSTATUS:") == 1
    assert "DESCRIPTION:Первая\\nВторая\\nSTATUS:CANCELLED" in value
    assert value.endswith("END:VCALENDAR\r\n")


def test_calendar_handles_overnight_end_folding_update_and_cancellation():
    e = event(event_time=time(23, 30), title="Ա" * 150)
    x = SimpleNamespace(end_time=time(1), address="ул. Тест", full_description=None,
                        updated_at=datetime(2026, 10, 20, tzinfo=timezone.utc))
    first = build_event_calendar(e, x)
    text = first.decode()
    assert "DTEND:20261024T210000Z" in text
    assert all(len(line) <= 75 for line in first.split(b"\r\n"))
    assert "SUMMARY:" + e.title in text.replace("\r\n ", "")
    e.status = EventStatus.CANCELLED
    e.updated_at = datetime(2026, 10, 21, tzinfo=timezone.utc)
    second = build_event_calendar(e, x).decode()
    assert "UID:era-event-42\r\n" in text and "UID:era-event-42\r\n" in second
    assert "STATUS:CANCELLED" in second
    assert "LAST-MODIFIED:20261021T000000Z" in second
    assert "SEQUENCE:1792540800" in second


def client_for(e, *, approved=True, registered=False):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    session = SimpleNamespace(get=AsyncMock(side_effect=[e, None]),
                              scalar=AsyncMock(return_value=object() if registered else None))
    async def session_override():
        yield session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, application_status=ApplicationStatus.APPROVED if approved else ApplicationStatus.PENDING)
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token="0000000000:TEST")
    return TestClient(app)


def test_calendar_endpoint_private_download_and_hidden_event_denial():
    response = client_for(event()).get("/api/v1/events/42/calendar.ics")
    assert response.status_code == 200
    assert "text/calendar" in response.headers["content-type"]
    assert "no-store" in response.headers["cache-control"]
    assert 'filename="ERA-42.ics"' in response.headers["content-disposition"]
    for status in (EventStatus.DRAFT, EventStatus.PENDING_APPROVAL):
        assert client_for(event(status=status), registered=True).get("/api/v1/events/42/calendar.ics").status_code == 404
    assert client_for(event(), approved=False).get("/api/v1/events/42/calendar.ics").status_code == 403
    assert client_for(event(status=EventStatus.CANCELLED)).get("/api/v1/events/42/calendar.ics").status_code == 404
    assert client_for(event(status=EventStatus.CANCELLED), registered=True).get("/api/v1/events/42/calendar.ics").status_code == 200
