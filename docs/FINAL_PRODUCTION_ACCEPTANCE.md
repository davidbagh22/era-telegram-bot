# ERA Platform — Final Production Acceptance

Closes the PR13–PR19 hardening block requested after the original 12-PR
Mini App plan (`docs/ERA_PLATFORM_PROGRESS.md`) was completed and merged.
This document is the single place that says, plainly, what "production
ready" does and does not mean for this codebase right now — per the
block's own rule: **the phrase "production ready" is only used here
because no unresolved Critical or High finding remains in
`docs/PRODUCTION_READINESS_AUDIT.md`.** Where that's not true (two
Medium-severity items are explicitly legal/organizational, not
technical), it's called out by name, not implied away.

## 1. What "production ready" covers here

| Area | Status | Evidence |
|---|---|---|
| Telegram `initData` verification, session tokens | Ready | `app/api/security.py`, timing-safe from the start |
| Auth bypass protection (`DEV_AUTH_ENABLED`) | Ready | Startup guard refuses to run misconfigured on Render — `Settings.assert_safe_for_deployment()` |
| Rate limiting | Ready | `/miniapp/auth` (PR13) + all 10 admin/leader decide/create endpoints (PR17). Participant-facing mutations explicitly out of scope — lower blast radius, see finding #11 |
| RBAC / object-level authorization (IDOR) | Ready | `docs/AUTHORIZATION_MATRIX.md` — load-by-ID-then-check pattern verified across every moderation endpoint |
| **Mini App actually renders for real users** | Ready (was broken) | Finding #18 — `base: "/app/"` fix, verified against the live prod domain before/after |
| **Mini App writes actually persist** | Ready (was broken) | Finding #19 — `get_session()` commit fix, the most severe bug this whole audit series found, caught by the E2E suite it also built |
| E2E test coverage | Ready | Playwright, real backend + real built frontend, one scenario per role, CI job `e2e` |
| Design system consistency | Ready | `docs/UI_DESIGN_SYSTEM.md`, dark theme support, safe-area handling |
| Silent action failures (dead buttons) | Ready | PR15 — 9 screens fixed, error-code-to-Russian-text translation |
| File/portfolio upload security | Ready | No server-side raw upload endpoint exists (architectural), re-confirmed under PR17b with grep evidence, not just asserted |
| Dependency vulnerabilities | Ready | `pip-audit --strict` clean and blocking; `npm audit --audit-level=high` clean and blocking (was non-blocking pending the Vite upgrade, now fixed — PR18b) |
| Database migrations | Ready | Single Alembic head (`0014_consent_log`); every migration in this block upgrade/downgrade-smoke-tested before merge |
| Backup & recovery | Ready | `docs/BACKUP_AND_RECOVERY.md` — daily automated backup + isolated-Postgres restore verification already running in CI (`database-backup.yml`), predates this block, left untouched |
| Chat access / moderation | Ready | Re-verified against current code in PR18c; live multi-account/real-broadcast verification is the one item genuinely outside this environment's reach — see §4 |
| Consent audit trail | **Technical foundation ready, not legally complete** | `ConsentLog` table + `record_consent()` (PR18) — placeholder policy version, no real policy text yet |
| Minors handling | **Technical foundation ready, not legally complete** | `is_minor()` (PR18) — informational only, no access restriction, no guardian-consent flow |
| Production domain/TLS, external error monitoring | **Not done from this environment** | Requires the owner's Render dashboard access — see §4 |

## 2. Full findings ledger

See `docs/PRODUCTION_READINESS_AUDIT.md` for the complete table (20
findings). Summary: 2 Critical (both Fixed, both found by this block's
own new E2E suite, not by manual review), 6 High (all Fixed), the rest
Medium/Low/Documented — none of the remaining open items are Critical or
High.

## 3. What was actually built, by block

| PR | What | Merge commit |
|---|---|---|
| PR13 | Security hardening audit — webhook timing-safe compare, `DEV_AUTH_ENABLED` guard, `/ready`, rate limiting on auth, chat-access audit logging, CI lint/dependency-audit | `2066103` |
| PR14 | Unified design system — dark theme, safe-area insets, `docs/UI_DESIGN_SYSTEM.md` | `288ab18` |
| PR15 | Functional stabilization — fixed silent action failures across 9 screens | `28de334` |
| PR16 | E2E test suite (Playwright) — **found and fixed both Critical bugs** (`base: "/app/"`, `get_session()` commit) | `47c385a` |
| PR17 | Rate limiting on all remaining admin/leader endpoints | `ea16735` |
| PR17b | File/portfolio upload security re-review (no code change — confirmed clean) | `a63a564` |
| PR18 | Consent log + minors technical scaffolding | `6bac2ed` |
| PR18b | Vite 5→8 upgrade, closed the last dependency advisory | `6c31c1c` |
| PR18c | Chat/registration/broadcast 12-point re-verification (no code change) | `4f44af5` |
| PR19 | This document + final regression | (recorded after merge) |

## 4. Explicit owner action items (not faked as done)

Each of these needs something only the platform owner can do — Render
dashboard access, a real Telegram test setup, or a legal decision. None
of them were silently skipped; each is named once, precisely, here:

1. **Production domain + TLS.** Render already terminates HTTPS on
   `*.onrender.com` — a custom domain needs DNS + Render dashboard
   configuration only the owner can do. See `docs/DEPLOYMENT_RUNBOOK.md`.
2. **External error monitoring** (Sentry-class tooling). Needs an
   account/DSN from the owner; nothing in this environment can create
   one. Baseline: unhandled exceptions are still logged with full
   tracebacks via Uvicorn's error logger, visible in Render's log viewer
   — not silent, just not proactively alerting.
3. **Real policy text for consent.** `ConsentLog` (PR18) is ready to
   record real consent the moment real text exists — swap
   `consent_service.CURRENT_POLICY_VERSION` and it's live. Writing that
   text is a legal decision, not a technical one.
4. **Minors/age-gating decision.** `is_minor()` (PR18) makes the data
   already collected (`birth_date`) visible to admins; whether to act on
   it (guardian consent, access restriction) is the owner's legal call.
5. **Bot's admin rights in the real Telegram chat(s).** Could not be
   checked from this environment — no `BOT_TOKEN`, no connected browser
   session (see PR18c). One-time check: open the chat's admin list in
   Telegram, confirm the bot has restrict/ban/pin rights.
6. **Live, multi-account chat-scenario testing** (item 8's "bot has
   admin rights" and full live walkthroughs of the 12-point checklist).
   Re-verified at the code level in PR18c with passing automated tests;
   a real click-through needs either the owner's own test or multiple
   real Telegram accounts this environment doesn't have.

## 5. Final regression (this block)

- `alembic heads` — single head (`0014_consent_log`).
- `ruff check app --select E9,F` — clean.
- `python -m compileall -q app` — clean.
- `pip-audit -r requirements.txt --strict` — 0 known vulnerabilities.
- `npm audit --audit-level=high` (frontend) — 0 vulnerabilities.
- Full `pytest -q` — **489 passed, 7 subtests passed, 0 failures** (final
  run for this block, confirmed immediately before opening this PR).
- CI (`test` ×2 workflows, `frontend`, `e2e`) green on every PR in this
  block, including this one.

## 6. Rollback

Nothing in this block changes the deployment topology. Standard rollback
per `docs/DEPLOYMENT_RUNBOOK.md`: Render Dashboard → Deploys → select the
previous successful deploy → Rollback. All migrations in this block
(`0014_consent_log`) are additive and downgrade-tested — `alembic
downgrade -1` is safe if ever needed, though nothing in this block
requires it.

## 7. What "production ready" explicitly does not claim

- Not claiming external monitoring exists — it doesn't yet.
- Not claiming a custom domain/TLS is configured from this environment
  — Render's default HTTPS is live; a custom domain is the owner's step.
- Not claiming legal compliance for consent or minors handling — the
  technical foundation exists, the legal decision doesn't yet.
- Not claiming every one of the addendum's 12 chat scenarios was
  clicked through live in a real Telegram client — code-level
  re-verification with passing tests, explicitly not the same thing,
  and said so at every point in this document rather than blurring it.
