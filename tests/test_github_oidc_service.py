from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.services.github_oidc_service import (
    EXPECTED_REF,
    EXPECTED_REPOSITORY,
    EXPECTED_REPOSITORY_ID,
    EXPECTED_WORKFLOW_REF,
    _require_exact_backup_claims,
)


def valid_claims(*, event_name: str = "push") -> dict[str, object]:
    return {
        "repository": EXPECTED_REPOSITORY,
        "repository_id": EXPECTED_REPOSITORY_ID,
        "ref": EXPECTED_REF,
        "workflow_ref": EXPECTED_WORKFLOW_REF,
        "runner_environment": "github-hosted",
        "event_name": event_name,
    }


class GitHubBackupOidcClaimsTests(unittest.TestCase):
    def test_path_scoped_main_push_identity_is_allowed(self) -> None:
        _require_exact_backup_claims(valid_claims(event_name="push"))

    def test_scheduled_and_manual_backup_identities_are_allowed(self) -> None:
        _require_exact_backup_claims(valid_claims(event_name="schedule"))
        _require_exact_backup_claims(valid_claims(event_name="workflow_dispatch"))

    def test_pull_request_event_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            _require_exact_backup_claims(valid_claims(event_name="pull_request"))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_repository_ref_or_workflow_stays_rejected(self) -> None:
        mutations = [
            {"repository": "attacker/repo"},
            {"repository_id": "999999"},
            {"ref": "refs/heads/feature"},
            {"workflow_ref": "davidbagh22/era-telegram-bot/.github/workflows/ci.yml@refs/heads/main"},
            {"runner_environment": "self-hosted"},
        ]
        for mutation in mutations:
            claims = valid_claims()
            claims.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(HTTPException) as ctx:
                _require_exact_backup_claims(claims)
            self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()