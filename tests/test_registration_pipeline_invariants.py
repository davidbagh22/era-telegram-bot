from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_new_registration_is_explicitly_routed_to_pending_queue() -> None:
    source = _read("app/repositories/users.py")
    assert "application_status=ApplicationStatus.PENDING" in source


def test_admin_application_queue_reads_pending_and_needs_info() -> None:
    source = _read("app/api/v1/admin_applications.py")
    assert "ApplicationStatus.PENDING" in source
    assert "ApplicationStatus.NEEDS_INFO" in source
    assert "User.is_archived.is_not(True)" in source


def test_registration_is_committed_before_telegram_notifications() -> None:
    source = _read("app/handlers/registration.py")
    commit_at = source.index("await session.commit()")
    notify_at = source.index("await _notify_admins_registration(")
    assert commit_at < notify_at


def test_registration_keeps_admin_notification_fallback() -> None:
    source = _read("app/handlers/registration.py")
    assert "send_admin_application_cards" in source
    assert "_fallback_registration_notice" in source
