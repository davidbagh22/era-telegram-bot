from app.handlers.admin.analytics_filters import _analytics_filter_keyboard, _analytics_keyboard, _system_keyboard, _enum_labels
from app.utils.constants import APPLICATION_STATUS_LABELS, ApplicationStatus


def _callbacks(keyboard) -> set[str]:
    return {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    }


def test_analytics_overview_has_filters_waiting_and_surveys() -> None:
    callbacks = _callbacks(_analytics_keyboard())
    assert "admin:analytics:waiting" in callbacks
    assert "admin:analytics:filters" in callbacks
    assert "admin:surveys" in callbacks
    assert "admin:analytics:excel:surveys" in callbacks


def test_analytics_filter_keyboard_has_management_slices() -> None:
    callbacks = _callbacks(_analytics_filter_keyboard())
    assert "admin:analytics:slice:roles" in callbacks
    assert "admin:analytics:slice:age" in callbacks
    assert "admin:analytics:slice:departments" in callbacks
    assert "admin:analytics:slice:tasks" in callbacks
    assert "admin:analytics:slice:surveys" in callbacks


def test_system_menu_promotes_waiting_and_surveys() -> None:
    callbacks = _callbacks(_system_keyboard())
    assert "admin:analytics" in callbacks
    assert "admin:analytics:waiting" in callbacks
    assert "admin:surveys" in callbacks
    assert "admin:goals" in callbacks


def test_enum_labels_use_readable_russian_names() -> None:
    labels = _enum_labels(ApplicationStatus, APPLICATION_STATUS_LABELS)
    assert labels["pending"] == "На рассмотрении"
    assert labels["approved"] == "Одобрена"
