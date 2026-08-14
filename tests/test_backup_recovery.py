from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackupRecoveryContractTests(unittest.TestCase):
    def test_backup_workflow_is_scheduled_oidc_verified_encrypted_and_tiered(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "database-backup.yml").read_text(encoding="utf-8")
        required = [
            "push:",
            'branches: [main]',
            '".github/workflows/database-backup.yml"',
            "schedule:",
            "id-token: write",
            "ACTIONS_ID_TOKEN_REQUEST_URL",
            "audience=era-platform-backup",
            "/snapshot",
            "scripts/verify_database_restore.sh",
            "/material",
            "openssl enc -aes-256-cbc",
            "-pbkdf2",
            "actions/upload-artifact@v7",
            "scripts/store_encrypted_backup_s3.sh",
            'TYPE="daily"',
            'TYPE="weekly"',
            'TYPE="monthly"',
            "/report",
        ]
        for marker in required:
            self.assertIn(marker, workflow)

        self.assertNotIn("BACKUP_DATABASE_URL", workflow)
        self.assertNotIn("BACKUP_REPORT_SECRET", workflow)
        self.assertNotIn("BACKUP_REPORT_URL", workflow)

        snapshot_pos = workflow.index("Download transient production snapshot using GitHub OIDC")
        restore_pos = workflow.index("Verify restore on isolated PostgreSQL")
        encrypt_pos = workflow.index("Encrypt verified backup package")
        artifact_pos = workflow.index("Upload encrypted verified GitHub artifact")
        self.assertLess(snapshot_pos, restore_pos)
        self.assertLess(restore_pos, encrypt_pos)
        self.assertLess(encrypt_pos, artifact_pos)

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

    def test_runtime_snapshot_never_exports_database_url(self) -> None:
        service = (ROOT / "app" / "services" / "backup_runtime_service.py").read_text(encoding="utf-8")
        for marker in ["PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD", "pg_dump", "--format=custom"]:
            self.assertIn(marker, service)
        self.assertNotIn('"database_url":', service)
        self.assertNotIn("print(database_url", service)

    def test_restore_script_checks_integrity_and_required_schema(self) -> None:
        script = (ROOT / "scripts" / "verify_database_restore.sh").read_text(encoding="utf-8")
        for marker in ["sha256sum", "pg_restore", "ON_ERROR_STOP=1", "public.users"]:
            self.assertIn(marker, script)

    def test_recovery_document_exists(self) -> None:
        document = (ROOT / "docs" / "BACKUP_AND_RECOVERY.md").read_text(encoding="utf-8")
        for marker in ["RPO", "RTO", "GitHub OIDC", "Восстановление", "Откат"]:
            self.assertIn(marker, document)


if __name__ == "__main__":
    unittest.main()