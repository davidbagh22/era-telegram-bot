from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ChatBindingProductionContractTests(unittest.TestCase):
    def test_four_org_chat_keys_persist_before_runtime_success(self) -> None:
        source = (ROOT / "app" / "handlers" / "chat_binding.py").read_text(encoding="utf-8")
        for marker in [
            '"general": ("general_chat_id", "general"',
            '"internal": ("internal_department_chat_id", "internal"',
            '"external": ("external_department_chat_id", "external"',
            '"leaders": ("leaders_chat_id", "leaders"',
            "AppSetting(key=setting_key, value=str(message.chat.id)",
            "await session.commit()",
            "setattr(settings, setting_key, message.chat.id)",
        ]:
            self.assertIn(marker, source)
        success_reply = 'f"✅ {title} привязан. Настройка сохранена в ЭРА'
        self.assertLess(source.index("await session.commit()"), source.index(success_reply))

    def test_startup_and_recovery_keep_database_as_source_of_truth(self) -> None:
        seed = (ROOT / "app" / "services" / "seed_service.py").read_text(encoding="utf-8")
        recovery = (ROOT / "app" / "services" / "chat_binding_recovery_service.py").read_text(encoding="utf-8")
        self.assertIn("select(AppSetting)", seed)
        self.assertIn("setattr(settings, item.key, value)", seed)
        self.assertIn("choose_unique_chat_id", recovery)
        self.assertIn("await session.commit()", recovery)

    def test_bind_confirmation_does_not_publish_numeric_chat_id(self) -> None:
        source = (ROOT / "app" / "handlers" / "chat_binding.py").read_text(encoding="utf-8")
        self.assertNotIn('ID: {message.chat.id}', source)


if __name__ == "__main__":
    unittest.main()