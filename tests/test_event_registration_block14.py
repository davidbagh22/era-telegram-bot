import inspect
import unittest

from app.handlers.admin.event_registration_block14 import _participants_keyboard, award_event_points
from app.handlers.participant import events_stability_block8
from app.services import event_card


def callbacks(keyboard):
    return [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]


class EventRegistrationBlock14Tests(unittest.TestCase):
    def test_event_card_supports_registered_count(self):
        signature = inspect.signature(event_card.format_event_text)
        self.assertIn("registered", signature.parameters)
        source = inspect.getsource(event_card.format_event_text)
        self.assertIn("Зарегистрировано", source)

    def test_public_event_view_uses_registration_stats(self):
        source = inspect.getsource(events_stability_block8.event_view)
        self.assertIn("registration_stats", source)
        self.assertIn("registered=", source)
        self.assertIn("can_register", source)

    def test_full_event_hides_registration_button(self):
        source = inspect.getsource(events_stability_block8.event_view)
        self.assertIn('int(stats["free"]) > 0', source)

    def test_admin_participants_keyboard_has_profiles_attendance_and_award(self):
        registration = type("RegistrationStub", (), {"id": 8})()
        participant = type(
            "UserStub", (), {"id": 4, "first_name": "Анна", "last_name": "Иванова"}
        )()
        values = callbacks(_participants_keyboard(3, [(registration, participant)]))
        self.assertIn("admin:user:4", values)
        self.assertIn("admin:event:attendance:attended:3:8", values)
        self.assertIn("admin:event:attendance:no_show:3:8", values)
        self.assertIn("admin:event:award:3", values)

    def test_event_points_award_is_idempotent(self):
        source = inspect.getsource(award_event_points)
        self.assertIn("event_points_already_awarded", source)
        self.assertIn("related_event_id=event.id", source)


if __name__ == "__main__":
    unittest.main()
