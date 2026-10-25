from app.handlers.admin.event_activities_stability import ALLOWED_TYPES, REVIEWABLE_ACTIVITY_STATUSES
from app.keyboards.admin import admin_activity_keyboard


def _callbacks(keyboard) -> set[str]:
    return {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    }


def test_activity_review_includes_leader_approved_status() -> None:
    assert REVIEWABLE_ACTIVITY_STATUSES == {"pending", "leader_approved"}


def test_activity_creation_accepts_expected_submission_types() -> None:
    assert {"photo", "video", "file", "text", "link", "manual"}.issubset(ALLOWED_TYPES)


def test_admin_activity_menu_points_to_review_flow() -> None:
    callbacks = _callbacks(admin_activity_keyboard())
    assert "admin:event_activities" in callbacks
