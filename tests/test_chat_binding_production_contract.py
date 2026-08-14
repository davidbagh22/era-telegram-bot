from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ChatBindingProductionContractTests(unittest.TestCase):
    def test_four_org_chat_keys_persist_to_app_settings(self) -> None:
        source = (ROOT / "app" / "handlers" / "chat_binding.py").read_text(encoding="utf-8")
        required = [
            '"general": ("general_chat_id", "general"',
            '"internal": ("internal_department_chat_id", "internal"',
            '"external": ("external_department_chat_id", "external"',
            '"leaders": ("leaders_chat_id", "leaders"',
            "AppSetting(key=setting_key, value=str(message.chat.id)",
            "stored.value = str(message.chat.id)",
            "await session.commit()",
            "setattr(settings, setting_key, message.chat.id)",
        ]
        for marker in required:
            self.assertIn(marker, source)

        # Never tell an admin that binding succeeded before the transaction is
        # durable in PostgreSQL.
        self.assertLess(source.index("await session.commit()"), source.index("await message.reply("))

    def test_startup_rehydrates_persisted_chat_settings(self) -> None:
        source = (ROOT / "app" / "services" / "seed_service.py").read_text(encoding="utf-8")
        self.assertIn("select(AppSetting)", source)
        self.assertIn("if hasattr(settings, item.key)", source)
        self.assertIn("setattr(settings, item.key, value)", source)

    def test_bind_confirmation_does_not_publish_numeric_chat_id(self) -> None:
        source = (ROOT / "app" / "handlers" / "chat_binding.py").read_text(encoding="utf-8")
        self.assertNotIn('ID: {message.chat.id}', source)


if __name__ == "__main__":
    unittest.main()