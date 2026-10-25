from pathlib import Path

import pytest

from app.services.event_qr_service import qr_png

ROOT = Path(__file__).resolve().parents[1]


def test_qr_attendance_is_retired_from_the_live_bot() -> None:
    participant_init = (ROOT / "app/handlers/participant/__init__.py").read_text(
        encoding="utf-8"
    )
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    qr_service = (ROOT / "app/services/event_qr_service.py").read_text(encoding="utf-8")

    assert "event_qr.router" not in participant_init
    assert "qrcode" not in requirements.casefold()
    assert "QR attendance is intentionally retired" in qr_service
    with pytest.raises(RuntimeError, match="retired"):
        qr_png("https://t.me/era_test_bot?start=old")


def test_attendance_code_flow_is_connected_to_api_and_mini_app() -> None:
    router = (ROOT / "app/api/v1/router.py").read_text(encoding="utf-8")
    service = (ROOT / "app/services/event_attendance_service.py").read_text(
        encoding="utf-8"
    )
    participant_ui = (
        ROOT / "frontend/src/screens/activity/EventsTab.tsx"
    ).read_text(encoding="utf-8")
    admin_ui = (
        ROOT / "frontend/src/screens/admin/events/EventParticipantsPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "event_attendance.router" in router
    assert "admin_event_attendance.router" in router
    assert "generate_attendance_code" in service
    assert "invalid_attendance_code" in service
    assert "event.attendance_confirmed" in service
    assert "EventAttendancePanel" in participant_ui
    assert "EventLifecyclePanel" in admin_ui
    assert "Начать мероприятие" in (
        ROOT / "frontend/src/screens/admin/events/EventLifecyclePanel.tsx"
    ).read_text(encoding="utf-8")
