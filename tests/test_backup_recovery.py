from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackupRecoveryContractTests(unittest.TestCase):
    def test_backup_workflow_is_scheduled_verified_encrypted_and_tiered(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "database-backup.yml").read_text(encoding="utf-8")
        required = [
            "schedule:",
            "BACKUP_DATABASE_URL",
            "scripts/backup_database.sh",
            "scripts/verify_database_restore.sh",
            "openssl enc -aes-256-cbc",
            "-pbkdf2",
            "actions/upload-artifact@v7",
            "scripts/store_encrypted_backup_s3.sh",
            'TYPE="daily"',
            'TYPE="weekly"',
            'TYPE="monthly"',
            "BACKUP_REPORT_SECRET",
        ]
        for marker in required:
            self.assertIn(marker, workflow)

        # A production dump must be encrypted before anything persisted by
        # upload-artifact or the external object-storage step.
        encrypt_pos = workflow.index("Encrypt verified backup package")
        artifact_pos = workflow.index("Upload encrypted verified GitHub artifact")
        external_pos = workflow.index("Store encrypted copy in external object storage")
        self.assertLess(encrypt_pos, artifact_pos)
        self.assertLess(encrypt_pos, external_pos)
        self.assertNotIn("retention-days: 30", workflow)

    def test_external_storage_script_enforces_exact_retention_counts(self) -> None:
        script = (ROOT / "scripts" / "store_encrypted_backup_s3.sh").read_text(encoding="utf-8")
        for marker in [
            "daily) KEEP_COUNT=7",
            "weekly) KEEP_COUNT=4",
            "monthly) KEEP_COUNT=6",
            "aws",
            "list-objects-v2",
            "delete-object",
        ]:
            self.assertIn(marker, script)

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
        for marker in [
            "RPO",
            "RTO",
            "BACKUP_DATABASE_URL",
            "Восстановление",
            "Откат",
            "7 daily / 4 weekly / 6 monthly",
        ]:
            self.assertIn(marker, document)


if __name__ == "__main__":
    unittest.main()
