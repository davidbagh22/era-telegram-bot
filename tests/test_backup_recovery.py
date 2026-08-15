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
            "Wait for matching production commit",
            'EXPECTED="${GITHUB_SHA}"',
            '"${PRODUCTION_BASE}/health"',
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
        self.assertNotIn("set -x", workflow)

        deploy_gate_pos = workflow.index("Wait for matching production commit")
        snapshot_pos = workflow.index("Download transient production snapshot using GitHub OIDC")
        restore_pos = workflow.index("Verify restore on isolated PostgreSQL 18")
        encrypt_pos = workflow.index("Encrypt verified backup package")
        artifact_pos = workflow.index("Upload encrypted verified GitHub artifact")
        self.assertLess(deploy_gate_pos, snapshot_pos)
        self.assertLess(snapshot_pos, restore_pos)
        self.assertLess(restore_pos, encrypt_pos)
        self.assertLess(encrypt_pos, artifact_pos)

    def test_backup_major_is_pinned_for_snapshot_and_restore(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        restore = (ROOT / "scripts" / "verify_database_restore.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "database-backup.yml").read_text(encoding="utf-8")
        self.assertIn("postgresql-client-18", dockerfile)
        self.assertIn("pg_dump --version", dockerfile)
        self.assertIn("postgres:18", restore)
        self.assertIn("Verify restore on isolated PostgreSQL 18", workflow)
        self.assertNotIn("image: postgres:16", workflow)
        self.assertNotIn("sudo apt-get install -y postgresql-client", workflow)

    def test_base_backup_does_not_depend_on_ubuntu_postgres_or_awscli_packages(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "database-backup.yml").read_text(encoding="utf-8")
        self.assertIn("sudo apt-get install -y jq", workflow)
        self.assertNotIn("sudo apt-get install -y postgresql-client jq", workflow)
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

    def test_runtime_snapshot_never_exports_database_url_or_logs_subprocess_stderr(self) -> None:
        service = (ROOT / "app" / "services" / "backup_runtime_service.py").read_text(encoding="utf-8")
        for marker in ["PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD", "pg_dump", "--format=custom", "verify_pg_dump_compatibility"]:
            self.assertIn(marker, service)
        self.assertNotIn('"database_url":', service)
        self.assertNotIn("print(database_url", service)
        self.assertIn("stderr=asyncio.subprocess.DEVNULL", service)

    def test_restore_script_checks_integrity_required_schema_and_has_no_trace_mode(self) -> None:
        script = (ROOT / "scripts" / "verify_database_restore.sh").read_text(encoding="utf-8")
        for marker in ["sha256sum", "pg_restore", "ON_ERROR_STOP=1", "public.users", "postgres:18"]:
            self.assertIn(marker, script)
        self.assertNotIn("set -x", script)

    def test_recovery_document_exists(self) -> None:
        document = (ROOT / "docs" / "BACKUP_AND_RECOVERY.md").read_text(encoding="utf-8")
        for marker in ["RPO", "RTO", "GitHub OIDC", "Восстановление", "Откат"]:
            self.assertIn(marker, document)


if __name__ == "__main__":
    unittest.main()
