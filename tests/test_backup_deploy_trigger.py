from pathlib import Path
import unittest

from app.services.github_oidc_service import _require_exact_backup_claims
from app.services.github_oidc_service import (
    EXPECTED_REF,
    EXPECTED_REPOSITORY,
    EXPECTED_REPOSITORY_ID,
    EXPECTED_WORKFLOW_REF,
)


ROOT = Path(__file__).resolve().parents[1]


class BackupDeployTriggerTests(unittest.TestCase):
    def test_workflow_listens_for_deployment_status_and_filters_render_main_success(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "database-backup.yml").read_text(encoding="utf-8")
        for marker in [
            "deployment_status:",
            "github.event.deployment_status.state == 'success'",
            "github.event.deployment.environment == 'main - era-telegram-bot'",
            "github.event.deployment.ref == 'main'",
        ]:
            self.assertIn(marker, workflow)

    def test_deployment_status_oidc_identity_is_allowed_only_on_exact_main_contract(self) -> None:
        claims = {
            "repository": EXPECTED_REPOSITORY,
            "repository_id": EXPECTED_REPOSITORY_ID,
            "ref": EXPECTED_REF,
            "workflow_ref": EXPECTED_WORKFLOW_REF,
            "runner_environment": "github-hosted",
            "event_name": "deployment_status",
        }
        _require_exact_backup_claims(claims)


if __name__ == "__main__":
    unittest.main()
