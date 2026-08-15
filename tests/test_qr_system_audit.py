from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_qr_system_is_not_implemented_and_is_documented() -> None:
    """Guard the unimplemented event-attendance QR feature specifically.

    `checkin` is intentionally not a generic QR marker anymore: My Vector has
    a legitimate monthly self-reflection Check-in that has nothing to do with
    QR attendance. The audit must detect QR implementation, not ban an
    unrelated product term across the entire application.
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
    qr_markers = ("qr_code", "qrcode", "qr token", "qr-token", "qr attendance")
    assert not any(marker in app_text for marker in qr_markers)

    progress = (ROOT / "docs" / "BOT_HARDENING_PROGRESS.md").read_text(
        encoding="utf-8"
    )
    assert "QR-система — не реализована" in progress
