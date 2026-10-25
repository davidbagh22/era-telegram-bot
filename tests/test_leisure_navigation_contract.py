from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from app.config import Settings
from app.handlers.book_club import _keyboard as literature_keyboard
from app.handlers.era_game_room import menu_markup
from app.handlers.era_leisure import _markup
from app.keyboards.bot_shell import main_inline_keyboard, main_reply_keyboard
from app.keyboards.participant import main_inline_keyboard as compatibility_menu


def buttons(markup):
    return [button for row in getattr(markup, "inline_keyboard", getattr(markup, "keyboard", [])) for button in row]


def test_main_menu_has_one_leisure_entry_and_no_flat_literature():
    for url in ("", "https://era.example/app/"):
        for admin in (False, True):
            root = buttons(main_inline_keyboard(admin=admin, miniapp_url=url))
            assert sum(button.callback_data == "leisure:home" for button in root) == 1
            assert not any(button.callback_data == "bookclub:home" for button in root)
            assert not any(button.callback_data == "bookclub:home" for button in buttons(compatibility_menu(admin=admin, miniapp_url=url)))
            reply = main_reply_keyboard(url, admin=admin)
            assert reply.is_persistent and reply.one_time_keyboard is False
            assert ("📊 Статистика" in {button.text for button in buttons(reply)}) == admin


class LeisureNavigationTests(IsolatedAsyncioTestCase):
    async def test_games_and_literature_share_the_leisure_section(self):
        settings = Settings(bot_token="1234567890:test-token", feature_games="ALL")
        markup = await _markup(SimpleNamespace(), settings, 11)
        callbacks = {button.callback_data for button in buttons(markup)}
        assert {"bookclub:home", "era_game:cabinet"} <= callbacks
        assert "leisure:home" in {button.callback_data for button in buttons(literature_keyboard())}
        assert "leisure:home" in {button.callback_data for button in buttons(menu_markup())}
        assert not any(button.callback_data == "leisure:home" for button in buttons(menu_markup(public=True)))
