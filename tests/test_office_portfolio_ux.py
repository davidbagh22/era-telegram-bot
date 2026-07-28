from pathlib import Path

from app.keyboards.participant import profile_sections_keyboard


ROOT = Path(__file__).resolve().parents[1]


def _buttons(keyboard):
    return [button for row in keyboard.inline_keyboard for button in row]


def test_profile_sections_exposes_direct_portfolio_pdf() -> None:
    buttons = _buttons(profile_sections_keyboard())
    callbacks = {button.callback_data for button in buttons if button.callback_data}
    labels = {button.text for button in buttons}

    assert "portfolio:resume" in callbacks
    assert "📄 Скачать PDF" in labels
    assert "cabinet:portfolio" in callbacks


def test_office_management_router_precedes_legacy_panel() -> None:
    source = (ROOT / "app/handlers/admin/__init__.py").read_text(encoding="utf-8")

    assert "offices_management.router" in source
    assert source.index("offices_management.router") < source.index("panel.router")


def test_office_delete_is_soft_and_keeps_assignment_history() -> None:
    source = (ROOT / "app/handlers/admin/offices_management.py").read_text(encoding="utf-8")

    assert 'callback_data=f"admin:office:delete:{office_id}"' in source
    assert 'callback_data=f"admin:office:delete_confirm:{office.id}"' in source
    assert "office.is_active = False" in source
    assert "assignment.is_active = False" in source
    assert "assignment.ends_at = date.today()" in source
    assert "session.delete(" not in source
    assert 'action="office.deleted"' in source


def test_office_view_keeps_assignment_end_action() -> None:
    source = (ROOT / "app/handlers/admin/offices_management.py").read_text(encoding="utf-8")

    assert 'callback_data=f"admin:office:remove:{assignment_id}"' in source
    assert "Завершить:" in source
    assert "🗑 Удалить должность" in source
