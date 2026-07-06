import unittest

from sqlalchemy import create_engine, inspect

from app.database import Base
from app.database.partners import Partner, PartnerInitiative, PartnerTask
from app.keyboards.participant import points_hub_keyboard, rewards_keyboard
from app.keyboards.partners import admin_partner_card_keyboard, partner_card_keyboard, partner_list_keyboard
from app.states.point_transfer import PointTransferStates


class PartnersAndPointTransferTests(unittest.TestCase):
    def test_partner_tables_are_registered(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        tables = set(inspect(engine).get_table_names())
        self.assertIn("partners", tables)
        self.assertIn("partner_initiatives", tables)
        self.assertIn("partner_tasks", tables)

    def test_partner_source_button_exists(self) -> None:
        partner = Partner(id=1, name="Partner", description="Desc", source_url="https://example.com")
        keyboard = partner_card_keyboard(partner)
        self.assertEqual(keyboard.inline_keyboard[0][0].url, "https://example.com")

    def test_partner_list_contains_partner_callback(self) -> None:
        partner = Partner(id=7, name="Partner", description="Desc", source_url="https://example.com")
        callbacks = [button.callback_data for row in partner_list_keyboard([partner]).inline_keyboard for button in row]
        self.assertIn("partner:view:7", callbacks)

    def test_admin_partner_controls_exist(self) -> None:
        callbacks = [button.callback_data for row in admin_partner_card_keyboard(3).inline_keyboard for button in row]
        self.assertIn("admin:partner:edit_url:3", callbacks)
        self.assertIn("admin:partner:toggle:3", callbacks)
        self.assertIn("admin:partner:archive:3", callbacks)

    def test_partner_initiative_and_task_models(self) -> None:
        initiative = PartnerInitiative(partner_id=1, title="Initiative", description="Desc")
        task = PartnerTask(partner_id=1, title="Task", description="Desc", points=20)
        self.assertEqual(initiative.partner_id, 1)
        self.assertEqual(task.points, 20)

    def test_partner_entry_is_in_rewards_menu(self) -> None:
        callbacks = [button.callback_data for row in rewards_keyboard([], []).inline_keyboard for button in row]
        self.assertIn("partners:list", callbacks)

    def test_point_transfer_states_and_button_exist(self) -> None:
        self.assertTrue(PointTransferStates.recipient.state)
        self.assertTrue(PointTransferStates.amount.state)
        self.assertTrue(PointTransferStates.confirm.state)
        callbacks = [button.callback_data for row in points_hub_keyboard().inline_keyboard for button in row]
        self.assertIn("points:transfer:start", callbacks)


if __name__ == "__main__":
    unittest.main()
