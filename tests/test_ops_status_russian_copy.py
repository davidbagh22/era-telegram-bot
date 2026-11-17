"""Ops status/backup panels must use Russian labels, not English tech words."""
from unittest import TestCase

from app.handlers.admin.commands_ready import _backup_text, _ops_keyboard, _status_text


class OpsStatusRussianCopyTests(TestCase):
    def test_ops_keyboard_uses_russian_backup_label(self) -> None:
        labels = [button.text for row in _ops_keyboard().inline_keyboard for button in row]
        self.assertTrue(any("Резерв" in text for text in labels))
        self.assertFalse(any(text == "Backup" or text.endswith("Backup") for text in labels))

    def test_status_text_localizes_health_and_check_status(self) -> None:
        text = _status_text({
            "latest": {
                "status": "healthy",
                "score": 91,
                "commit_sha": "abcdef1234567890",
                "checks": [{"name": "postgres", "status": "ok"}, {"name": "redis", "status": "fail"}],
            },
            "incidents": [],
        })
        self.assertIn("Оценка: 91/100", text)
        self.assertIn("Сборка: abcdef123456", text)
        self.assertIn("postgres: в норме", text)
        self.assertIn("redis: сбой", text)
        self.assertNotIn("Health:", text)
        self.assertNotIn("Commit:", text)
        self.assertNotIn(": ok", text)
        self.assertNotIn(": fail", text)

    def test_backup_text_uses_russian_headings(self) -> None:
        empty = _backup_text({"backups": []})
        self.assertIn("Резервные копии ЭРА", empty)
        self.assertNotIn("Backup", empty)
        filled = _backup_text({
            "backups": [{
                "status": "success",
                "backup_type": "full",
                "storage_provider": "s3",
                "completed_at": "2026-11-17",
                "size_bytes": 10,
                "commit_sha": "deadbeefcafe",
                "restore_verified_at": "2026-11-17",
            }]
        })
        self.assertIn("Статус: успешно", filled)
        self.assertIn("Проверка восстановления:", filled)
        self.assertNotIn("Restore verification", filled)


class VersionAndDailySummaryCopyTests(TestCase):
    def test_version_command_uses_russian_labels(self) -> None:
        source = open("app/handlers/admin/version_command.py", encoding="utf-8").read()
        self.assertIn("Сборка:", source)
        self.assertIn("Приём обновлений:", source)
        self.assertNotIn("Commit:", source)
        self.assertNotIn("Menu button:", source)
        self.assertNotIn("Service:", source)

    def test_daily_summary_avoids_english_health_backup_words(self) -> None:
        source = open("app/services/system_health_service.py", encoding="utf-8").read()
        self.assertIn("Последняя резервная копия:", source)
        self.assertNotIn("Health:", source)
        self.assertNotIn("Последний backup:", source)
        self.assertNotIn("restore verification", source)
