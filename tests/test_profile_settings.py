import unittest

from sqlalchemy import create_engine, inspect

from app.database import Base
from app.database.socials import SocialLink, SocialProfile
from app.keyboards.participant import profile_sections_keyboard, profile_settings_keyboard, rewards_keyboard
from app.utils.validators import normalize_email


class ProfileSettingsTests(unittest.TestCase):
    def test_profile_tables_are_registered(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        tables = set(inspect(engine).get_table_names())
        self.assertIn("social_profiles", tables)
        self.assertIn("social_links", tables)

    def test_profile_photo_is_file_id(self) -> None:
        profile = SocialProfile(user_id=1, photo_file_id="file-id")
        self.assertEqual(profile.photo_file_id, "file-id")

    def test_social_link_model(self) -> None:
        link = SocialLink(user_id=1, platform="Telegram", url="https://t.me/era")
        self.assertEqual(link.platform, "Telegram")

    def test_profile_settings_keyboard_entry_exists(self) -> None:
        labels = [button.text for row in profile_sections_keyboard().inline_keyboard for button in row]
        self.assertIn("⚙️ Настройки профиля", labels)
        settings = [button.text for row in profile_settings_keyboard().inline_keyboard for button in row]
        self.assertIn("Фото", settings)
        self.assertIn("Соцсети", settings)
        self.assertIn("Email", settings)

    def test_email_validation_rejects_bad_values(self) -> None:
        self.assertEqual(normalize_email("Name@Example.COM"), "name@example.com")
        self.assertIsNone(normalize_email("bad-email"))
        self.assertIsNone(normalize_email("mail.ru"))

    def test_reward_auctions_are_button_rows(self) -> None:
        class Auction:
            id = 1
            title = "Auction"

        keyboard = rewards_keyboard([], [Auction()])
        self.assertTrue(all(isinstance(row, list) for row in keyboard.inline_keyboard))


if __name__ == "__main__":
    unittest.main()
