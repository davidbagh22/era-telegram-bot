from pathlib import Path

from app.services.event_qr_service import qr_png
from app.utils.deep_links import (
    attendance_deep_link,
    attendance_payload,
    parse_attendance_payload,
)

ROOT = Path(__file__).resolve().parents[1]


def test_attendance_payload_is_signed_and_telegram_safe() -> None:
    secret = "test-secret"
    payload = attendance_payload(123456789, secret)

    assert payload.startswith("att_123456789_")
    assert len(payload.encode("utf-8")) <= 64
    assert parse_attendance_payload(payload, secret) == 123456789
    assert parse_attendance_payload(payload, "other-secret") is None


def test_attendance_payload_rejects_tampering() -> None:
    secret = "test-secret"
    payload = attendance_payload(42, secret)
    tampered = payload.replace("att_42_", "att_43_", 1)

    assert parse_attendance_payload(tampered, secret) is None
    assert parse_attendance_payload("att_not-a-number_bad", secret) is None
    assert parse_attendance_payload("anything", secret) is None


def test_attendance_deep_link_and_qr_are_real_telegram_assets() -> None:
    link = attendance_deep_link("@era_test_bot", 42, "test-secret")

    assert link.startswith("https://t.me/era_test_bot?start=att_42_")
    assert qr_png(link).startswith(b"\x89PNG\r\n\x1a\n")


def test_qr_attendance_is_connected_to_the_live_bot() -> None:
    participant_init = (ROOT / "app/handlers/participant/__init__.py").read_text(
        encoding="utf-8"
    )
    emergency = (ROOT / "app/handlers/emergency.py").read_text(encoding="utf-8")
    qr_handler = (ROOT / "app/handlers/participant/event_qr.py").read_text(
        encoding="utf-8"
    )
    qr_service = (ROOT / "app/services/event_qr_service.py").read_text(
        encoding="utf-8"
    )

    assert "event_qr.router" in participant_init
    assert "parse_attendance_payload" in emergency
    assert "event_qr_service.check_in" in emergency
    assert 'Command("qr")' in qr_handler
    assert "attendance_deep_link" in qr_handler
    assert "RegistrationStatus.ATTENDED" in qr_service
    assert "event.selfie_required" in qr_service
