# ERA Platform MASTER audit remediation

This branch closes verified gaps found during the MASTER audit against the current `main` implementation.

## Non-negotiable invariants

- Global Admin Command Center access is admin-only; narrow permission grants never escalate into global analytics/exports.
- Application status shown to a participant must match `ApplicationStatus` exactly. Internal rejection reasons are never exposed.
- Verified operational scoring remains idempotent and uses the single `PointTransaction` ledger.
- A Project Curator progression rank receives the 1.05 multiplier only on explicitly role-scoped responsibility work; stronger leadership-role multipliers do not stack with it.
- Media Chat access requires approved Media membership (or Media lead/admin), not merely an approved ERA application.
- Admin attention/health cards must have real navigation targets rather than no-op callbacks.
- Meaningful Activity, participation lifecycle/reactivation, Community Verification and versioned onboarding reuse their existing engines; this remediation must not introduce parallel implementations.

## Regression coverage added

`tests/test_master_audit_regressions.py` locks the permission boundary, truthful application-status presentation, curator multiplier behavior and Media Chat membership boundary.
