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


def test_only_guarded_excel_functions_are_mounted_in_analytics_router() -> None:
    from app.handlers.admin.analytics_filters import router
    from app.handlers.admin.management_ready import analytics_excel
    from app.handlers.admin.surveys_analytics import survey_excel
    from app.handlers.admin.legacy_action_bridge import LEGACY_ADMIN_ACTIONS
    callbacks = [handler.callback for handler in router.callback_query.handlers]
    assert callbacks.count(analytics_excel) == 1
    assert callbacks.count(survey_excel) == 1
    assert 'admin:analytics:excel:all' not in LEGACY_ADMIN_ACTIONS
    assert 'admin:analytics:excel:surveys' not in LEGACY_ADMIN_ACTIONS
