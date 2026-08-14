from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackupRecoveryContractTests(unittest.TestCase):
    def test_backup_workflow_is_scheduled_verified_encrypted_recorded_and_tiered(self) -> None:
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
            "scripts/record_backup_history.sh",
            "Record verified backup in ERA Backup History",
            'TYPE="daily"',
            'TYPE="weekly"',
            'TYPE="monthly"',
        ]
        for marker in required:
            self.assertIn(marker, workflow)

        # A production dump must be restore-tested and encrypted before any
        # copy is persisted. Backup History may only be marked successful
        # after persistence has completed.
        restore_pos = workflow.index("Verify restore on isolated PostgreSQL")
        encrypt_pos = workflow.index("Encrypt verified backup package")
        artifact_pos = workflow.index("Upload encrypted verified GitHub artifact")
        external_pos = workflow.index("Store encrypted copy in external object storage")
        history_pos = workflow.index("Record verified backup in ERA Backup History")
        self.assertLess(restore_pos, encrypt_pos)
        self.assertLess(encrypt_pos, artifact_pos)
        self.assertLess(encrypt_pos, external_pos)
        self.assertLess(artifact_pos, history_pos)
        self.assertLess(external_pos, history_pos)
        self.assertNotIn("retention-days: 30", workflow)

        # Backup metadata persistence is authoritative and must not depend on
        # an HTTP callback secret. The optional internal callback endpoint has
        # its own fail-closed authorization tests.
        self.assertNotIn("BACKUP_REPORT_SECRET", workflow)
        self.assertNotIn("X-ERA-Backup-Secret", workflow)

    def test_backup_history_script_uses_parameterized_upsert_without_logging_credentials(self) -> None:
        script = (ROOT / "scripts" / "record_backup_history.sh").read_text(encoding="utf-8")
        for marker in [
            "set -Eeuo pipefail",
            "psql",
            "--set=ON_ERROR_STOP=1",
            "INSERT INTO backup_history",
            "ON CONFLICT (backup_key) DO UPDATE",
            ":'backup_key'",
            ":'backup_status'",
        ]:
            self.assertIn(marker, script)
        self.assertNotIn("echo ${DATABASE_URL}", script)
        self.assertNotIn("printf '%s\\n' \"${DATABASE_URL}\"", script)

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