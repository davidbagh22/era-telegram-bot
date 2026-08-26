from app.handlers.admin import router as admin_router
from app.keyboards.bot_shell import main_inline_keyboard
from app.webapp import ADMIN_COMMANDS, USER_COMMANDS


def _labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_start_keyboard_stays_three_action_gateway_for_admins_and_leaders() -> None:
    markup = main_inline_keyboard(
        privileged=True,
        admin=True,
        miniapp_url="https://era.example/app/",
    )
    assert _labels(markup) == [
        "🔥 Открыть ЭРА",
        "🧭 Навигация",
        "💬 Связь",
    ]


def test_slash_autocomplete_stays_three_commands_for_every_private_user() -> None:
    expected = ["start", "navigation", "contact"]
    assert [command.command for command in USER_COMMANDS] == expected
    assert [command.command for command in ADMIN_COMMANDS] == expected


def test_bot_admin_root_mounts_only_compatibility_bridge() -> None:
    names = [subrouter.name for subrouter in admin_router.sub_routers]
    assert names == ["admin_legacy_action_bridge"]
