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


def test_office_management_router_is_wired_and_legacy_panel_is_not() -> None:
    source = (ROOT / "app/handlers/admin/__init__.py").read_text(encoding="utf-8")

    assert "offices_management.router" in source
    assert "panel.router" not in source
    assert "panel," not in source


def test_office_list_is_owned_by_modern_router_and_exposes_delete() -> None:
    source = (ROOT / "app/handlers/admin/offices_management.py").read_text(encoding="utf-8")

    assert '@router.callback_query(F.data == "admin:offices")' in source
    assert 'text="🗑"' in source
    assert 'callback_data=f"admin:office:delete:{office.id}"' in source
    assert "Кнопка 🗑 справа" in source


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


def test_runtime_version_command_is_admin_only_and_wired() -> None:
    admin_init = (ROOT / "app/handlers/admin/__init__.py").read_text(encoding="utf-8")
    version_source = (ROOT / "app/handlers/admin/version_command.py").read_text(encoding="utf-8")
    webapp = (ROOT / "app/webapp.py").read_text(encoding="utf-8")

    assert "version_command.router" in admin_init
    assert 'Command("version")' in version_source
    assert "can_manage_people" in version_source
    assert "RENDER_GIT_COMMIT" in version_source
    assert 'BotCommand(command="version"' in webapp
    assert '"commit": DEPLOYED_COMMIT' in webapp
