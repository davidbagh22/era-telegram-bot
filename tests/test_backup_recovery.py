from pathlib import Path
import unittest

from app.services.backup_runtime_service import _classify_pg_dump_failure


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
            "Wait for matching production commit",
            'EXPECTED="${GITHUB_SHA}"',
            '"${PRODUCTION_BASE}/health"',
            "/snapshot",
            "scripts/verify_database_restore.sh",
            "/material",
            "openssl enc -aes-256-cbc",
            "openssl enc -d -aes-256-cbc",
            "DECRYPTED_SHA",
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

        deploy_gate_pos = workflow.index("Wait for matching production commit")
        snapshot_pos = workflow.index("Download transient production snapshot using GitHub OIDC")
        restore_pos = workflow.index("Verify restore on isolated PostgreSQL")
        encrypt_pos = workflow.index("Encrypt and verify backup package")
        artifact_pos = workflow.index("Upload encrypted verified GitHub artifact")
        self.assertLess(deploy_gate_pos, snapshot_pos)
        self.assertLess(snapshot_pos, restore_pos)
        self.assertLess(restore_pos, encrypt_pos)
        self.assertLess(encrypt_pos, artifact_pos)

    def test_backup_clients_are_pinned_to_supported_major(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "database-backup.yml").read_text(encoding="utf-8")
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn('PG_MAJOR: "18"', workflow)
        self.assertIn("image: postgres:18", workflow)
        self.assertIn('postgresql-client-${PG_MAJOR}', workflow)
        self.assertIn("ARG PG_MAJOR=18", dockerfile)
        self.assertIn('"postgresql-client-${PG_MAJOR}"', dockerfile)
        self.assertNotIn("\n    postgresql-client \\", dockerfile)

    def test_base_backup_does_not_depend_on_ubuntu_awscli_package(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "database-backup.yml").read_text(encoding="utf-8")
        self.assertNotIn("sudo apt-get install -y postgresql-client jq awscli", workflow)
        self.assertIn("Install AWS CLI for external storage only", workflow)
        self.assertIn("if: steps.config.outputs.external_storage == 'true'", workflow)
        self.assertIn("python3 -m venv /tmp/era-awscli", workflow)
        self.assertIn("/tmp/era-awscli/bin/python -m pip install", workflow)

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
        for marker in [
            "PGHOST",
            "PGDATABASE",
            "PGUSER",
            "PGPASSWORD",
            "pg_dump",
            "--format=custom",
            "_classify_pg_dump_failure",
            "pg_dump_version_mismatch",
        ]:
            self.assertIn(marker, service)
        self.assertNotIn('"database_url":', service)
        self.assertNotIn("print(database_url", service)

    def test_pg_dump_failure_classification_is_safe_and_regression_protected(self) -> None:
        mismatch = b"pg_dump: error: server version: 18.1; pg_dump version: 15.9; aborting because of server version mismatch"
        self.assertEqual(_classify_pg_dump_failure(mismatch), "pg_dump_version_mismatch")
        self.assertEqual(
            _classify_pg_dump_failure(b"password authentication failed for user era"),
            "pg_dump_auth_failed",
        )
        self.assertEqual(
            _classify_pg_dump_failure(b"unexpected error DATABASE_URL=postgres://user:secret@example/db"),
            "pg_dump_failed",
        )
        self.assertNotIn("secret", _classify_pg_dump_failure(b"secret token key"))

    def test_restore_script_checks_integrity_schema_and_migration_heads(self) -> None:
        script = (ROOT / "scripts" / "verify_database_restore.sh").read_text(encoding="utf-8")
        for marker in [
            "sha256sum",
            "pg_restore",
            "--exit-on-error",
            "ON_ERROR_STOP=1",
            "public.users",
            "alembic_version",
            "alembic heads",
            "CODE_HEADS",
            "RESTORED_HEADS",
        ]:
            self.assertIn(marker, script)
        self.assertNotIn("SELECT COUNT(*) AS users_count", script)

    def test_snapshot_failure_logs_only_allow_listed_machine_codes(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "database-backup.yml").read_text(encoding="utf-8")
        self.assertIn("SAFE_CODE", workflow)
        self.assertIn("snapshot_http_error", workflow)
        self.assertNotIn('cat "${RESPONSE_FILE}"', workflow)
        self.assertNotIn("DATABASE_URL", workflow)

    def test_recovery_document_exists(self) -> None:
        document = (ROOT / "docs" / "BACKUP_AND_RECOVERY.md").read_text(encoding="utf-8")
        for marker in ["RPO", "RTO", "GitHub OIDC", "Восстановление", "Откат"]:
            self.assertIn(marker, document)


if __name__ == "__main__":
    unittest.main()
