from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_qr_system_is_not_implemented_and_is_documented() -> None:
    """QR attendance remains intentionally absent.

    My Vector now has a personal monthly reflection flow. The QR audit stays
    focused on concrete attendance/QR implementation markers instead of
    generic product terminology used by unrelated features.
    """
    qr_files = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "app").rglob("*.py")
        if "qr" in path.name.lower()
    ]
    assert qr_files == []

    app_text = "\n".join(
        path.read_text(encoding="utf-8").casefold()
        for path in (ROOT / "app").rglob("*.py")
    )
    qr_markers = (
        "qr_code",
        "qrcode",
        "pyzbar",
        "segno",
        "event_checkin",
        "attendance_checkin",
        "qr attendance",
        "qr-attendance",
    )
    assert not any(marker in app_text for marker in qr_markers)

    progress = (ROOT / "docs" / "BOT_HARDENING_PROGRESS.md").read_text(
        encoding="utf-8"
    )
    assert "QR-система — не реализована" in progress
