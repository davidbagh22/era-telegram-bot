from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackupRecoveryContractTests(unittest.TestCase):
    def test_backup_workflow_is_scheduled_and_verifies_restore(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "database-backup.yml").read_text(encoding="utf-8")
        required = [
            "schedule:",
            "BACKUP_DATABASE_URL",
            "scripts/backup_database.sh",
            "scripts/verify_database_restore.sh",
            "actions/upload-artifact@v4",
            "retention-days: 30",
        ]
        for marker in required:
            self.assertIn(marker, workflow)

    def test_backup_script_uses_safe_postgres_dump_contract(self) -> None:
        script = (ROOT / "scripts" / "backup_database.sh").read_text(encoding="utf-8")
        for marker in ["set -Eeuo pipefail", "pg_dump", "--format=custom", "sha256sum", "--no-owner"]:
            self.assertIn(marker, script)
        self.assertNotIn("echo ${DATABASE_URL}", script)

    def test_restore_script_checks_integrity_and_required_schema(self) -> None:
        script = (ROOT / "scripts" / "verify_database_restore.sh").read_text(encoding="utf-8")
        for marker in ["sha256sum", "pg_restore", "ON_ERROR_STOP=1", "public.users"]:
            self.assertIn(marker, script)

    def test_recovery_document_exists(self) -> None:
        document = (ROOT / "docs" / "BACKUP_AND_RECOVERY.md").read_text(encoding="utf-8")
        for marker in ["RPO", "RTO", "BACKUP_DATABASE_URL", "Восстановление", "Откат"]:
            self.assertIn(marker, document)


if __name__ == "__main__":
    unittest.main()
