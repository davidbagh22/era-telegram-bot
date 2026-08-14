import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import bot as bot_module
from app.handlers import chat, emergency
from app.handlers.leader import events_block6
from app.utils import texts
from app.utils.constants import ApplicationStatus, Role


class FakeState:
    def __init__(self):
        self.data = {}
        self.current = None
        self.clear_count = 0

    async def clear(self):
        self.clear_count += 1
        self.data = {}
        self.current = None

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def set_state(self, value):
        self.current = value

    async def get_data(self):
        return dict(self.data)


class FakeMessage:
    def __init__(self, text="", chat_type="private"):
        self.text = text
        self.caption = None
        self.photo = None
        self.from_user = SimpleNamespace(id=1593868942)
        self.chat = SimpleNamespace(id=1, type=chat_type)
        self.answers = []
        self.new_chat_members = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class FakeBot:
    async def get_me(self):
        return SimpleNamespace(username="era_test_bot")


def approved_user(role=Role.PARTICIPANT):
    return SimpleNamespace(
        id=1,
        role=role,
        application_status=ApplicationStatus.APPROVED,
        is_blocked=False,
        is_archived=False,
        permission_grants=[],
    )


class FsmRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_clears_event_date_state(self):
        state = FakeState()
        state.current = events_block6.EventBlock6States.date
        message = FakeMessage("/start")
        with patch.object(emergency, "_subscription_ok", AsyncMock(return_value=True)), patch.object(
            emergency, "_send_main_menu", AsyncMock()
        ) as send_menu:
            await emergency.rescue_start(
                message,
                FakeBot(),
                approved_user(),
                SimpleNamespace(era_channel_url="https://t.me/example"),
                state,
            )
        self.assertEqual(state.clear_count, 1)
        send_menu.assert_awaited_once()
        self.assertNotIn("Проверьте формат", " ".join(x[0] for x in message.answers))

    async def test_menu_clears_event_date_state(self):
        state = FakeState()
        state.current = events_block6.EventBlock6States.date
        message = FakeMessage("/menu")
        with patch.object(emergency, "_subscription_ok", AsyncMock(return_value=True)), patch.object(
            emergency, "_send_main_menu", AsyncMock()
        ):
            await emergency.rescue_start(
                message,
                FakeBot(),
                approved_user(),
                SimpleNamespace(era_channel_url="https://t.me/example"),
                state,
            )
        self.assertEqual(state.clear_count, 1)

    async def test_reply_buttons_clear_event_date_state(self):
        settings = SimpleNamespace(
            internal_department_chat_url="https://t.me/internal",
            external_department_chat_url="https://t.me/external",
        )
        for label in emergency.MENU_BUTTONS:
            with self.subTest(label=label):
                state = FakeState()
                state.current = events_block6.EventBlock6States.date
                message = FakeMessage(label)
                with patch.object(emergency, "_send_personal_cabinet", AsyncMock()), patch.object(
                    emergency, "_send_event_list", AsyncMock()
                ), patch.object(emergency, "_send_main_menu", AsyncMock()), patch.object(
                    emergency, "total_points", AsyncMock(return_value=0)
                ):
                    await emergency.rescue_menu_button(
                        message,
                        approved_user(),
                        settings,
                        SimpleNamespace(),
                        state,
                    )
                self.assertEqual(state.clear_count, 1)
                self.assertNotIn(
                    "Проверьте формат",
                    " ".join(x[0] for x in message.answers),
                )

    async def test_panel_button_redirects_admin_to_miniapp(self):
        # emergency.router is registered first (test_emergency_router_is_first
        # below) and its StateFilter("*") matches any FSM state, so this
        # handler -- not navigation.py's panel_button -- is what a real
        # "⚙️ Панель" tap actually reaches. Must redirect, not show the old
        # admin_panel_keyboard() tree. 2026-08 master spec, P5.
        settings = SimpleNamespace(effective_miniapp_url="https://era-app.example/")
        state = FakeState()
        message = FakeMessage("⚙️ Панель")
        await emergency.rescue_menu_button(
            message, approved_user(Role.ADMIN), settings, SimpleNamespace(), state
        )
        (text, kwargs) = message.answers[-1]
        self.assertEqual(text, texts.ADMIN_PANEL_MOVED)
        markup = kwargs["reply_markup"]
        self.assertIsNotNone(markup)
        buttons = [b for row in markup.inline_keyboard for b in row]
        self.assertTrue(all(b.web_app is not None for b in buttons))

    async def test_panel_button_redirects_leader_to_miniapp(self):
        settings = SimpleNamespace(effective_miniapp_url="https://era-app.example/")
        state = FakeState()
        message = FakeMessage("⚙️ Панель")
        await emergency.rescue_menu_button(
            message, approved_user(Role.LEADER), settings, SimpleNamespace(), state
        )
        (text, kwargs) = message.answers[-1]
        self.assertEqual(text, texts.LEADER_PANEL_MOVED)
        markup = kwargs["reply_markup"]
        self.assertIsNotNone(markup)
        buttons = [b for row in markup.inline_keyboard for b in row]
        self.assertTrue(all(b.web_app is not None for b in buttons))

    async def test_cancel_clears_any_state(self):
        state = FakeState()
        state.current = events_block6.EventBlock6States.date
        message = FakeMessage("/cancel")
        settings = SimpleNamespace(era_channel_url="https://t.me/example")
        with patch.object(emergency, "_send_main_menu", AsyncMock()):
            await emergency.cancel_any(message, approved_user(), settings, state)
        self.assertEqual(state.clear_count, 1)
        self.assertIn("Текущее действие отменено", message.answers[0][0])

    async def test_event_date_stored_as_string(self):
        state = FakeState()
        message = FakeMessage("22/05/2026")
        await events_block6.date_step(
            message,
            approved_user(Role.LEADER),
            state,
        )
        self.assertEqual(state.data["date"], "2026-05-22")
        self.assertIsInstance(state.data["date"], str)

    async def test_event_time_stored_as_string(self):
        state = FakeState()
        message = FakeMessage("18:30")
        await events_block6.time_step(
            message,
            approved_user(Role.LEADER),
            state,
        )
        self.assertEqual(state.data["time"], "18:30")
        self.assertIsInstance(state.data["time"], str)

    async def test_start_in_group_does_not_start_registration(self):
        state = FakeState()
        message = FakeMessage("/start", chat_type="group")
        await emergency.group_start(message, FakeBot(), state)
        self.assertEqual(state.clear_count, 1)
        self.assertIn("личном чате", message.answers[0][0])
        markup = message.answers[0][1]["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].text, "Открыть бот")

    async def test_new_chat_member_welcome(self):
        message = FakeMessage(chat_type="group")
        message.new_chat_members = [
            SimpleNamespace(id=10, first_name="Анна", is_bot=False),
            SimpleNamespace(id=11, first_name="Бот", is_bot=True),
        ]
        session = SimpleNamespace(scalar=AsyncMock(return_value=None))
        settings = SimpleNamespace(
            leaders_chat_id=None,
            internal_department_chat_id=None,
            external_department_chat_id=None,
        )
        await chat.welcome_members(message, FakeBot(), settings, session)
        self.assertEqual(len(message.answers), 1)
        self.assertIn("Добро пожаловать в ЭРА", message.answers[0][0])

    async def test_rescue_start_real_menu_includes_miniapp_button(self):
        # Regression test for the actual live-config bug: emergency.router
        # is registered first (see test_emergency_router_is_first below,
        # which is itself intentional, not a bug), so rescue_start — not
        # start.py's start() — is what a real approved user's /start
        # actually reaches. rescue_start's call to _send_main_menu()
        # dropped `settings`, so the Mini App button never appeared no
        # matter how many times main_inline_keyboard() itself was fixed —
        # this is the only test in the whole suite that exercises
        # the real router-selected handler without mocking _send_main_menu
        # away, so it is the only one that would have caught this.
        state = FakeState()
        message = FakeMessage("/start")
        settings = SimpleNamespace(
            era_channel_url="https://t.me/example",
            effective_miniapp_url="https://era-telegram-bot.onrender.com/app/",
        )
        with patch.object(emergency, "_subscription_ok", AsyncMock(return_value=True)):
            await emergency.rescue_start(message, FakeBot(), approved_user(), settings, state)
        markup = message.answers[-1][1]["reply_markup"]
        buttons = [button for row in markup.inline_keyboard for button in row]
        miniapp_button = next((b for b in buttons if b.text == "🔥 Открыть ЭРА"), None)
        self.assertIsNotNone(miniapp_button, "Mini App button missing from the real /start reply")
        self.assertEqual(miniapp_button.web_app.url, settings.effective_miniapp_url)

    def test_emergency_router_is_first(self):
        source = inspect.getsource(bot_module.create_dispatcher)
        self.assertLess(
            source.index("emergency.router"),
            source.index("start.router"),
        )


if __name__ == "__main__":
    unittest.main()
