# ERA PLATFORM — FINAL PRODUCTION ACCEPTANCE

**NOT READY FOR LAUNCH**

Checks: **217 / 300 PASS**
FAIL: **25**
N/A: **24** (each with a stated reason, per the checklist's own rule)
OWNER ACTION REQUIRED: **34**

Critical open issues: **1**
High open issues: **4**

Production commit: `bb19003` (verified live via `/health`/`/diag` at the time this document was written — see §XX)
Database migration: single Alembic head, `0014_consent_log` — verified via `python -m alembic heads`
Backup timestamp: **none successful — see Critical finding below**
Restore test: **FAIL** (never run — nothing to restore)
Bot: **PASS** (live, correct identity/webhook/menu button per `/diag`)
Mini App: **PASS** (live, builds clean, served at `/app`)
Participant E2E: **PASS** (CI, against real backend + real built frontend)
Leader E2E: **PASS** (CI)
Admin E2E: **PASS** (CI)
Chat restrictions: **PASS at code level** (re-verified PR18c); **not live-clicked-through this pass** — see §XVII
Broadcasts: **PASS at code level**; not live-verified this pass
Portfolio/files: **PASS architecturally** (no raw-upload endpoint exists — see §X); **upload/view/delete flow has no E2E coverage** — disclosed gap
Data protection technical controls: **PASS (technical foundation only)** — see §VIII, §IX
Legal review: **OWNER ACTION REQUIRED**

---

## Why NOT READY FOR LAUNCH

One **Critical** and four **High** items are open. Per the checklist's own
stop-ship rule, that alone is disqualifying regardless of how many of the
other 294 items pass. Named here first, in full, not buried in the tables:

### CRITICAL

**The database backup pipeline has not produced a single successful backup
in at least 10 days.** `docs/BACKUP_AND_RECOVERY.md` and the prior
`docs/FINAL_PRODUCTION_ACCEPTANCE.md` (PR19, since superseded by this
document) both describe `.github/workflows/database-backup.yml` as "already
running." That was true of the *code*. It was not true of the *pipeline*:

```
$ gh run list --workflow=database-backup.yml --limit 10
completed  failure  Database backup  main  schedule  2026-08-11T03:10:35Z
completed  failure  Database backup  main  schedule  2026-08-10T03:18:27Z
completed  failure  Database backup  main  schedule  2026-08-09T03:07:46Z
... (10/10 checked, all failure, back to 2026-08-02)
```

Every run fails at the **"Validate backup secret"** step. `gh secret list`
on this repository returns empty — the `BACKUP_DATABASE_URL` GitHub Actions
secret that `docs/BACKUP_AND_RECOVERY.md`'s own "Первичная настройка"
section says must be created was never actually created. This means:
there is currently **no backup of production data, at all** — not "an old
one," none. This is item #299 and the checklist's own explicit stop-ship
condition ("отсутствует рабочий backup"; "backup существует, но никто не
доказал возможность восстановления" — in this case it's the first half:
it doesn't exist).

**Fix**: the platform owner sets `BACKUP_DATABASE_URL` (a Render Postgres
external connection string, read-only user if the schema supports it — see
`docs/BACKUP_AND_RECOVERY.md`) as a GitHub Actions secret, then manually
re-runs the workflow once to confirm a green run before trusting the
schedule again. This is entirely an owner action — nothing in this
environment can create or read Render/GitHub secrets.

### HIGH

1. **Legal review has not happened.** `docs/PRIVACY_POLICY_DRAFT.md` is
   explicitly a draft with `[...]` placeholders, undetermined jurisdiction,
   and a note that it "обязателен к проверке юристом" before real use.
   `docs/DATA_INVENTORY.md` §5–6 confirm consent-text and minors handling
   are technical scaffolding only (`ConsentLog` table exists,
   `policy_version` is a placeholder constant `"unset-v1"`). No org/legal
   owner of data processing is named anywhere in the repo. Items #121–135
   are collectively not passable by a coding session — they need the
   platform owner and, per the checklist's own rule, a lawyer.
2. **No incident response / business-continuity documentation exists.**
   `docs/` has no incident-response runbook; there is no documented
   scenario for bot-token leak, admin-account compromise, DB compromise, or
   hosting-provider outage (§XIX, items #279–283). `render.yaml`'s
   `ADMIN_IDS` is a single Telegram ID — no evidence anywhere of a second
   owner, MFA, or recovery codes for the accounts this platform depends on
   (Render, GitHub, BotFather). This is a real single-point-of-failure risk
   for a "must survive 24-48h unattended" requirement (#240), not a
   theoretical one.
3. **No live device/real-Telegram-client testing was performed in this
   pass.** This environment has no Telegram account, no BOT_TOKEN-holding
   session, and no physical/emulated device. Everything marked PASS in
   §IV/§XVIII that says "live" or "real Telegram client" is PASS *only* in
   the sense of automated E2E against a real backend + real built frontend
   (Playwright, headless Chromium, 390×844 viewport) — genuinely valuable,
   genuinely not the same thing as a human opening the actual bot on an
   actual phone, and the checklist itself says so explicitly ("локально
   работает ≠ PASS... Необходима проверка production-версии"). Items
   #267–269, #294–298 need the owner's own click-through.
4. **CI's `test` job (and the separate `tests.yml`) still run
   `python -m unittest discover`, which silently collects zero tests from
   17 of the repository's test files** (any file not subclassing
   `unittest.TestCase`). This was found and flagged mid-session as a
   background task (`task_6f10a296`, "Switch CI test runner from unittest
   discover to pytest") — the user started it in a separate session; as of
   this document it has not landed (`.github/workflows/ci.yml` and
   `tests.yml` both still say `unittest discover` as of commit `bb19003`).
   This does not mean the code is broken — this session ran the *full*
   `pytest -q` locally repeatedly (743 passed, most recently right before
   merging PR 38) and every merged PR's local full-suite run was green
   before merge — but it does mean **CI's own green checkmark has been
   systematically incomplete**, and #196/#256/#257 can only be marked PASS
   with that caveat stated, not silently.

None of these four are "nice to have later" items. Per the checklist's own
rule, this is `NOT READY FOR LAUNCH` until the Critical is closed and each
High is either closed or the owner explicitly accepts the risk in writing.

---

## Methodology

Every row below has one of `PASS` / `FAIL` / `N/A` / `OWNER ACTION
REQUIRED`, per the checklist's own rule that `N/A` must state why. Evidence
is cited tersely (file, command, or doc) rather than reproduced at length —
full detail lives in the cited source. Where this session's own commands
were the evidence, the exact command is named so it can be re-run.

Existing docs consulted and treated as authoritative unless this pass found
them stale (the backup finding above is exactly one case where a prior
doc's claim didn't hold up to a fresh check — noted inline where relevant):
`AUTHORIZATION_MATRIX.md`, `DATA_INVENTORY.md`, `PRODUCTION_READINESS_AUDIT.md`
(dated 2026-08-05, baseline commit `e401b2f`), `BACKUP_AND_RECOVERY.md`,
`DEPLOYMENT_RUNBOOK.md`, `PRIVACY_POLICY_DRAFT.md`, `ROLE_PERMISSION_MATRIX.md`,
`UI_DESIGN_SYSTEM.md`, `BOT_VS_MINIAPP_AUDIT.md`, `ERA_PLATFORM_PROGRESS.md`
(the full PR-by-PR history through PR 38).

Fresh commands run for this document (all against commit `bb19003` unless
noted): `python -m alembic heads`; `ruff check app --select E9,F`;
`python -m compileall -q app`; `pip-audit -r requirements.txt --strict`;
`npm audit --audit-level=high` (frontend); `gh run list
--workflow=database-backup.yml`; `gh secret list`; `gh run view <id>
--log-failed`; `git grep` for hardcoded secrets, `console.log`, `TODO`/
`FIXME`; `curl https://era-telegram-bot.onrender.com/{health,ready,diag}`.

---

## I. Продукт и готовность к запуску (1–15)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Scope of first production version fixed | PASS | `docs/BOT_VS_MINIAPP_AUDIT.md` + `ERA_PLATFORM_PROGRESS.md`'s PR 36–38 sections |
| 2 | List of Mini App features compiled | PASS | `docs/BOT_VS_MINIAPP_AUDIT.md` (per-feature table) |
| 3 | List of Bot features compiled | PASS | same doc |
| 4 | No unjustified Bot↔Mini App duplication | PASS | PR 36's audit + keyboard rewrite; remaining "duplication" (bot fallback menu) is explicitly justified as the offline fallback |
| 5 | Mini App is the primary user interface | PASS | `App.tsx` routes every role into the Mini App; PR 36 keyboard no longer advertises the bot's own menu tree when Mini App is configured |
| 6 | Bot used as gateway/notifications/quick actions/fallback | PASS | PR 36 `main_menu()`; `docs/BOT_VS_MINIAPP_AUDIT.md`'s "What Bot keeps" list |
| 7 | Known limitations of v1 recorded | PASS | Each PR section in `ERA_PLATFORM_PROGRESS.md` has a "Deliberately not touched" subsection; Excel-export gap explicitly named since PR 29 |
| 8 | Unfinished features are hidden, not fake | PASS | No stub buttons found (`git grep` for disabled-but-visible actions); Excel export is disclosed as Bot-only, not hidden |
| 9 | No mock data in production | PASS | `git grep -n "console.log\|mock" frontend/src` clean; `scripts/e2e_seed.py` only ever runs against `DATABASE_URL=sqlite+aiosqlite:///./e2e.db` in CI/local, never invoked against the production `DATABASE_URL` |
| 10 | No test users in production interface | OWNER ACTION REQUIRED | Can't query the live production Postgres from this environment to confirm no leftover `9000xx`-range test users exist there — the seed script has only ever been run against throwaway SQLite in this session, but the owner should confirm the production DB itself is clean |
| 11 | No buttons without a working backend action | PASS | PR 15 (prior session block) fixed all found instances; PR 36–38 didn't add new ones (each new button traced to a real handler/route in this session) |
| 12 | No placeholder screens | PASS | No screen in `frontend/src/screens/` renders static "coming soon" content |
| 13 | No production-critical `TODO`/`FIXME` | PASS | `grep -rn "TODO\|FIXME" app --include=*.py` (excluding tests) → empty |
| 14 | Owner assigned per functional block | OWNER ACTION REQUIRED | No named individuals anywhere in the repo beyond a single `ADMIN_IDS` Telegram ID in `render.yaml` — this is an organizational decision only the platform owner can make |
| 15 | Final READY/NOT READY criteria fixed | PASS | This document |

## II. Bot ↔ Mini App архитектура (16–30)

| # | Item | Status | Evidence |
|---|---|---|---|
| 16 | Full bot handler list checked for duplication | PASS | `docs/BOT_VS_MINIAPP_AUDIT.md` — every participant/leader/admin handler area tabled |
| 17 | Legacy bot screens removed from user-facing UX | PASS | PR 36: old `👤 Личный кабинет`/`⚙️ Панель` tree no longer on the default keyboard |
| 18 | Bot fallback not removed before Mini App confirmed stable | PASS | PR 36 explicitly kept the old menu as the `else` (no-Mini-App-URL) branch |
| 19 | `/start` gives a clear path into ERA Platform | PASS | `app/handlers/start.py::start()` |
| 20 | Bot's main button opens Mini App | PASS | PR 36 `main_menu()`, first row |
| 21 | `🔥 Открыть ЭРА` button verified | PASS | `tests/test_participant_menu_miniapp_button.py` (button is a real `WebAppInfo`, not a callback) |
| 22 | Telegram Menu Button verified | PASS | `/diag` → `"menu_button_type":"web_app","menu_button_verified":true` (checked live against Telegram at process boot) |
| 23 | Main Mini App in bot profile verified | PASS | `/diag` → `"miniapp_configured":true` |
| 24 | Deep links from Bot to specific Mini App screens | PASS (partial) | Tab-level deep links shipped in PR 36 (`#/tasks`, `#/events`, `#/opportunities`) and verified by `frontend/e2e/deep_links.spec.ts`; **per-notification item-level deep linking (a specific task/event/opportunity) is prepared (`miniapp_task_url`/`miniapp_event_url`/`miniapp_opportunity_url` helpers exist) but not yet wired into notification call sites** — that was planned as PR 40, not reached this session |
| 25 | Return from Mini App to Telegram | PASS | Native Telegram WebView back button; no custom code needed or found missing |
| 26 | Bot works when frontend temporarily unavailable | PASS | `_mount_frontend()` in `app/webapp.py` doesn't raise if `frontend/dist` is absent — bot/API continue |
| 27 | Bot works when backend temporarily unavailable | N/A | Bot and backend are the same process (`docs/DEPLOYMENT_RUNBOOK.md`, "Топология") — the question doesn't apply architecturally |
| 28 | No Bot→Mini App→Bot cycles | PASS | Reviewed deep-link flows; each hop terminates in a screen, not a redirect loop |
| 29 | Single source of truth for business logic | PASS | Bot handlers and Mini App API routes both call the same `app/services/*.py` functions throughout this session's work (e.g. `home_service.py` reused by both surfaces) |
| 30 | No separate Mini App user table | PASS | One `users` table, one Postgres, shared by both surfaces (`app/database/models.py`) |

## III. UI / UX / Design System (31–45)

| # | Item | Status | Evidence |
|---|---|---|---|
| 31 | All screens use one design system | PASS | `docs/UI_DESIGN_SYSTEM.md` (PR 37); tokens/components used throughout `frontend/src/screens` |
| 32 | Colors fixed | PASS | `frontend/src/theme/tokens.css` |
| 33 | Typography scale fixed | PASS | PR 37, `--era-text-xs`…`--era-text-3xl` |
| 34 | Spacing system fixed | PASS | PR 37, `--era-space-1`…`--era-space-8` |
| 35 | Border radius fixed | PASS | `--era-radius-sm/control/card/pill/sheet` |
| 36 | Buttons unified | PASS | `.era-btn-primary` + global `button` rule in `tokens.css` |
| 37 | Inputs/forms unified | PASS | Global `input`/`textarea`/`select` rules in `tokens.css` |
| 38 | Cards unified | PASS | `components/Card.tsx` |
| 39 | Status badges unified | PASS | `components/StatusBadge.tsx` |
| 40 | Modal/bottom-sheet UX unified | PASS | PR 37 `Modal.tsx`/`BottomSheet.tsx`, one real usage (event-registration cancel confirm) |
| 41 | Loading/skeleton states | PASS (partial rollout) | PR 37 `Skeleton*` components exist and are wired into Home/Profile/Events/Tasks; the remaining ~40 screens still show the older plain-text loading state pending PR 38/39-style content passes |
| 42 | Empty states | PASS | `components/EmptyState.tsx`, used across the app |
| 43 | Error states | PASS | `components/StatusBanner.tsx` (full-screen) + inline error text (panel-level) |
| 44 | Success/confirmation states | PASS | PR 37 `Toast`/`useToast()`, used for register/cancel/résumé-download |
| 45 | Visual review of every production screen before release | OWNER ACTION REQUIRED | This environment has no working local backend+Redis+real-device pipeline to render and screenshot all ~45 screens against live data — a genuine click-through by the owner (or a future session with that infra) is needed before claiming this |

## IV. Telegram Mini App (46–60)

| # | Item | Status | Evidence |
|---|---|---|---|
| 46 | Production Mini App URL uses HTTPS | PASS | `https://era-telegram-bot.onrender.com` (Render terminates TLS) |
| 47 | Mini App URL matches deployed frontend | PASS | `curl https://era-telegram-bot.onrender.com/health` → `"commit":"bb19003"`, matching `git log -1` on `main` |
| 48 | Correct production bot token in use | PASS | `/diag` → `bot_id: 8481922061`, `bot_username: "ERA_1bot"` — matches the expected production bot |
| 49 | `getMe()` confirms correct production bot | PASS | Same `/diag` fields, computed from a real `getMe()` call at process boot (`app/webapp.py::lifespan`) |
| 50 | Telegram Menu Button returns correct `web_app` | PASS | `/diag` → `menu_button_type: "web_app"`, `menu_button_verified: true` |
| 51 | Main Mini App configured on the correct bot | PASS | `/diag` → `miniapp_configured: true` |
| 52 | `initData` passed to backend without unsafe transforms | PASS | `frontend/src/hooks/useAuth.ts` forwards the raw `initData` string; `app/api/security.py` parses it server-side |
| 53 | `initData` validated exclusively on backend | PASS | `app/api/security.py::verify_init_data` — HMAC-SHA256 over the WebAppData secret |
| 54 | `initDataUnsafe` not used as a trust source | PASS | Confirmed in `PRODUCTION_READINESS_AUDIT.md`'s pre-existing-good list; not reintroduced this session |
| 55 | `auth_date` checked | PASS | `app/api/security.py`, `init_data_max_age_seconds` (default 3600s per `PRODUCTION_READINESS_AUDIT.md` finding #5) |
| 56 | Expired Telegram auth rejected | PASS | Same check, covered by `tests/test_miniapp_security.py` |
| 57 | Forged hash/signature rejected | PASS | `hmac.compare_digest`-based check; covered by tests |
| 58 | Telegram ID stored as a safe integer type | PASS | `User.telegram_id: Mapped[int]` (`app/database/models.py`) |
| 59 | Telegram theme light/dark compatibility | PASS | `tokens.css`'s `:root[data-theme="dark"]`, driven by `telegram/webApp.ts::applyTelegramTheme()` (PR 14, re-documented in PR 37) |
| 60 | Safe-area/viewport on real Telegram clients | PASS at code level; OWNER ACTION REQUIRED for live confirmation | `env(safe-area-inset-*)` used throughout (PR 14 audit); no real device available in this environment to confirm visually |

## V. Authentication & Session Security (61–75)

| # | Item | Status | Evidence |
|---|---|---|---|
| 61 | User cannot supply an arbitrary Telegram ID | PASS | Telegram ID comes only from verified `initData`, never a request field, except `devTelegramId` which is gated by `DEV_AUTH_ENABLED` (see #73) |
| 62 | User cannot self-assign an arbitrary role | PASS | `app/api/v1/schemas.py`'s `MiniAppUserOut` derives role from the DB row, never from client input; role-change endpoints are admin-only (`AUTHORIZATION_MATRIX.md`) |
| 63 | Frontend is not the source of truth for authentication | PASS | All auth decisions happen in `app/api/deps.py`/`security.py`, server-side |
| 64 | Frontend is not the source of truth for authorization | PASS | `AUTHORIZATION_MATRIX.md` — every check is a backend `can_*`/`is_full_admin` call |
| 65 | Session lifetime checked | PASS | `create_session_token(..., ttl_seconds=...)` in `app/api/security.py` |
| 66 | Session expiry behaves correctly | PASS | Covered by `tests/test_miniapp_security.py` |
| 67 | Re-authentication checked | PASS | `useAuth.ts` re-runs `/miniapp/auth` on visibility/focus (this is also the mechanism PR16's `pending_sync.spec.ts` proves) |
| 68 | Session revocation | N/A | Sessions are stateless signed tokens with a short TTL, not server-side session records — there is nothing to "revoke" by design; the practical equivalent (rotating `MINIAPP_AUTH_SECRET`) invalidates all sessions at once, documented in `PRODUCTION_READINESS_AUDIT.md` finding #12 |
| 69 | Logout, if applicable | N/A | No logout concept exists (or is needed) for a Telegram WebApp identity — closing the Mini App is the equivalent |
| 70 | Secret tokens not in URLs | PASS | Session token travels as an `Authorization: Bearer` header (`app/api/deps.py`), not a query string |
| 71 | Long-lived server secrets not in `localStorage` | PASS | Nothing in `frontend/src` writes to `localStorage` for secrets (`git grep -n "localStorage" frontend/src` — only used, if at all, for non-secret UI state) |
| 72 | Cookie flags secure, if cookies used | N/A | No cookies are used anywhere in this stack (Bearer-token auth only) |
| 73 | `DEV_AUTH_ENABLED` fully off in production | PASS | `Settings.assert_safe_for_deployment()` — refuses to start if `DEV_AUTH_ENABLED=true` and Render env detected (`app/config.py`) |
| 74 | Test auth-bypass mechanisms unavailable in production | PASS | Same guard; `devTelegramId` is a no-op unless `DEV_AUTH_ENABLED=true`, which production startup refuses |
| 75 | Auth failure events logged without secrets | PASS | `app/api/security.py`'s error paths don't log the raw `initData` or session token (spot-checked; no `logger` call includes `init_data` or `token` variables) |

## VI. RBAC / Rights / IDOR (76–90)

| # | Item | Status | Evidence |
|---|---|---|---|
| 76 | Current Authorization Matrix exists | PASS | `docs/AUTHORIZATION_MATRIX.md` |
| 77 | Participant has only participant permissions | PASS | Matrix table, row-by-row |
| 78 | Leader access limited to permitted projects | PASS | `project_workspace_service.py::can_manage_project`/`can_view_workspace` |
| 79 | Admin endpoints unreachable by Participant | PASS | `require_dashboard_access`-style dependencies on every `admin.py` route |
| 80 | Leader endpoints unreachable by plain Participant | PASS | `leader.py` routes gated by `PRIVILEGED_ROLES` check |
| 81 | Rights checked per-object, not just per-endpoint | PASS | "Object-level authorization" pattern in `AUTHORIZATION_MATRIX.md` — load-by-ID then check, applied consistently |
| 82 | Cannot open another user's private profile via ID swap | PASS | `app/api/v1/profile.py` derives the target from `get_current_user()`, never a path/query ID |
| 83 | Cannot open another user's portfolio via ID swap | PASS | Same mechanism |
| 84 | Leader cannot alter another leader's project via ID swap | PASS | `can_manage_project()` checks the specific `project_id` against the caller's assignment |
| 85 | Cannot alter another user's application | PASS | Admin decide-endpoints require reviewer role; the applicant identity comes from the loaded object, not the caller |
| 86 | Cannot alter another user's task | PASS | `decide_task_application` checks `task.creator_id == actor.id` (leader) or admin role |
| 87 | Cannot self-assign an admin role via API | PASS | Role-change endpoints are `is_full_admin`-only, and `can_change_role` explicitly forbids changing one's own role (`AUTHORIZATION_MATRIX.md`) |
| 88 | No mass-assignment of forbidden fields | PASS | Every mutating endpoint uses a narrow Pydantic request model, not a generic "patch the ORM object" pattern (spot-checked `app/api/v1/*.py`) |
| 89 | Sensitive operations deny-by-default | PASS | `AUTHORIZATION_MATRIX.md`'s stated principle, consistent with every endpoint reviewed |
| 90 | Negative security tests exist for every role | PASS (not exhaustive) | `tests/test_authorization_service.py`, `tests/test_rate_limit.py`, `tests/test_admin_leader_rate_limiting.py` plus per-endpoint 403/404 assertions scattered through `tests/test_*_api.py`; **not a single consolidated "every role × every endpoint" matrix test** — real coverage exists, but auditing it as literally exhaustive would overstate it |

## VII. API Security (91–105)

| # | Item | Status | Evidence |
|---|---|---|---|
| 91 | Inventory of all production endpoints | PASS | `app/api/v1/router.py` aggregates every route; enumerable via `python -c "from app.webapp import app; [print(r.path) for r in app.routes]"` |
| 92 | Deprecated endpoints removed/closed | PASS | No endpoint found returning a deprecation stub; API surface reviewed each PR this session |
| 93 | Debug endpoints removed | PASS | `docs_url=None, openapi_url=None` (`app/webapp.py`); `/diag` is intentionally non-sensitive (see its own docstring) |
| 94 | Validation on every user input | PASS | Pydantic request models throughout; `clean_text()` helper for free-text fields |
| 95 | Max string length limited | PASS | `clean_text(..., N)` calls with explicit caps (e.g. 255/1500 chars, per `PRODUCTION_READINESS_AUDIT.md` finding #20) |
| 96 | Max request body size limited | N/A | No file-upload endpoint exists to make this a meaningful concern (see §X); JSON bodies are small, structured Pydantic models |
| 97 | Pagination for potentially large lists | PASS (bounded limits, not full cursor pagination) | `home_service.py`, `leader_service.py`, `task_review_service.py` etc. cap queries at 30–50 rows; `user_management_service.py` has real `limit`/`offset` pagination |
| 98 | Rate limiting on authentication | PASS | `/api/v1/miniapp/auth` (PR13), `tests/test_rate_limit.py` |
| 99 | Rate limiting on admin-critical actions | PASS | All `admin.py`/`leader.py` decide/create endpoints (PR17), `tests/test_admin_leader_rate_limiting.py` |
| 100 | Rate limiting on expensive endpoints | PASS (partial, documented exception) | Covers auth + all admin/leader mutations; participant-facing mutations (register for event, apply to opportunity, etc.) are explicitly **not** rate-limited — a known, documented exception (`PRODUCTION_READINESS_AUDIT.md` finding #11's own scope note: "lower blast radius") |
| 101 | SQL injection protection | PASS | SQLAlchemy ORM/Core with bound parameters throughout; `git grep -n "f\".*SELECT\|execute(f\"" app` found no raw string-interpolated SQL |
| 102 | XSS protection | PASS | React escapes all rendered content by default; no `dangerouslySetInnerHTML` found in `frontend/src` |
| 103 | Command/template injection protection | PASS | No `subprocess`/`os.system`/`eval`/template-string execution of user input found in `app/` |
| 104 | API doesn't return excess model fields | PASS | Every response uses a narrow `*Out` Pydantic schema (`PRODUCTION_READINESS_AUDIT.md` finding #9) |
| 105 | API errors don't leak stack traces/SQL/secrets/paths | PASS | FastAPI's default production error handling (no `debug=True` found in `app/webapp.py`); errors return structured `HTTPException` details, not tracebacks |

## VIII. Personal Data (106–120)

| # | Item | Status | Evidence |
|---|---|---|---|
| 106 | Full Data Inventory exists | PASS | `docs/DATA_INVENTORY.md` |
| 107 | Processing purpose defined per field | PASS | Same doc, §1–2 |
| 108 | Unnecessary collected data removed | PASS | Doc explicitly notes no unused-field bloat found |
| 109 | Required vs. optional fields defined | PASS | Doc §1 table, "Обязательное" column |
| 110 | Personal data identified | PASS | Doc §1, "Категория" column |
| 111 | Sensitive data separately identified | PASS | `birth_date`/`age` flagged "Чувствительные" |
| 112 | Access per data type defined | PASS | Doc §1–2 |
| 113 | Admin doesn't see data they don't need | PASS (mostly) | `*Out` schemas scope admin views; `is_minor()` (PR18) is the one deliberate exception, and it's disclosed, not hidden |
| 114 | API minimizes returned PII | PASS | Same schema discipline as §VII #104 |
| 115 | PII not in technical logs unnecessarily | PASS | `initData`, session tokens confirmed not logged (§V #75); general app logs don't include user free-text fields |
| 116 | PII not in analytics/monitoring automatically | N/A | No analytics/monitoring tool is integrated at all yet (§XVI) — there's nothing for PII to leak into |
| 117 | Retention periods defined per data category | FAIL | `docs/DATA_INVENTORY.md` §7 is explicitly a *proposal*, not an implemented policy — "Ниже — рабочее предложение... не внедрённая политика" |
| 118 | Data deletion process implemented | FAIL | Same doc §4: "Нет реализованного самообслуживаемого экспорта/удаления данных" — manual-only via direct DB access |
| 119 | Data export/access process implemented | FAIL | Same — no self-service export exists |
| 120 | Post-account-deletion data fate defined | FAIL | Not defined anywhere in the repo |

## IX. Legal Readiness (121–135)

| # | Item | Status | Evidence |
|---|---|---|---|
| 121 | Operating legal entity/organization defined | OWNER ACTION REQUIRED | `PRIVACY_POLICY_DRAFT.md` line 16–18: literal placeholder `[указать точное юридическое название организации...]` |
| 122 | Applicable jurisdiction confirmed with a lawyer | OWNER ACTION REQUIRED | Same doc, explicitly unresolved: "юрисдикция ЭРА не определена" |
| 123 | Compliance with Armenian PDPA checked | OWNER ACTION REQUIRED | No compliance review exists in the repo; jurisdiction itself isn't even confirmed yet |
| 124 | Final Privacy Policy prepared | FAIL | Draft only, with placeholders |
| 125 | Privacy Policy reviewed by a lawyer | OWNER ACTION REQUIRED | Not done — the draft says so itself |
| 126 | User consent to data processing prepared | FAIL | `ConsentLog` table technically ready (PR18); no real consent *text* exists to consent to |
| 127 | Consent version tracked | PASS (mechanism only) | `consent_service.py::record_consent()` stores `policy_version`; currently a placeholder value `"unset-v1"`, not real content |
| 128 | Consent date/time tracked | PASS | `ConsentLog.created_at` |
| 129 | Consenting user tracked | PASS | `ConsentLog.user_id` |
| 130 | Consent withdrawal rules defined | FAIL | Not defined anywhere |
| 131 | Legal model for minors checked separately | OWNER ACTION REQUIRED | `DATA_INVENTORY.md` §6: explicitly not resolved, "не может быть закрыто одним техническим PR" |
| 132 | Minimum self-registration age defined | FAIL | No age gate exists anywhere in registration flow |
| 133 | Guardian consent flow implemented if needed | FAIL | Not implemented; `is_minor()` is informational-only, admin-visible, non-blocking (PR18) |
| 134 | Legal basis for publishing participant photos/video checked | OWNER ACTION REQUIRED | Not addressed anywhere in the repo |
| 135 | Written legal `APPROVED / RISKS ACCEPTED` obtained | OWNER ACTION REQUIRED | Does not exist |

## X. Files / Photos / Portfolio (136–150)

| # | Item | Status | Evidence |
|---|---|---|---|
| 136 | Allowlist of permitted file types | N/A | No raw file-upload endpoint exists in the Mini App API at all — confirmed by `git grep -rn "UploadFile\|multipart"  app/api` returning nothing. All media flows through Telegram's own `file_id` mechanism (`PRODUCTION_READINESS_AUDIT.md` finding #10, re-confirmed in PR17b finding #20) |
| 137 | MIME type checked, not just extension | N/A | Same — no upload path to check |
| 138 | Max file size limited | N/A | Telegram itself enforces this for any bot-received file; nothing server-side to bound |
| 139 | Image dimensions limited | N/A | Same |
| 140 | User filename not used as a filesystem path | N/A | No filenames are ever used as paths — files aren't written to this app's filesystem at all |
| 141 | Storage protected from path traversal | N/A | No server-side file storage exists to traverse |
| 142 | Executable file upload forbidden | N/A | Same — no upload path |
| 143 | HTML/SVG upload risk checked | N/A | Same |
| 144 | Private files don't have an uncontrolled public URL | PASS | `PortfolioItem.url` field exists but is never populated by any of the ~10 creation call sites (`PRODUCTION_READINESS_AUDIT.md` finding #20) — effectively dead, not a live exposure |
| 145 | Authorization checked on file download | N/A | Files are served by Telegram directly via `file_id`, not by this app |
| 146 | Cannot download another user's private file via ID swap | N/A | Same — this app never serves file bytes |
| 147 | Portfolio item deletion handles the physical file correctly | N/A | No physical file to handle — only a DB row and a Telegram `file_id` reference |
| 148 | Unneeded metadata/EXIF stripped | N/A | This app never touches file bytes to strip anything from |
| 149 | A corrupted file doesn't crash the app | N/A | Same — no file parsing happens server-side |
| 150 | Dedicated file upload/download security tests | N/A | Nothing to test at this layer; the actual security property (no raw upload surface exists) is what PR17b's finding #20 verified with `grep` evidence, and that's the real control here |

## XI. Database / Data Integrity (151–165)

| # | Item | Status | Evidence |
|---|---|---|---|
| 151 | Production uses the expected PostgreSQL database | PASS | `render.yaml`'s `era-postgres` service, wired via `DATABASE_URL` |
| 152 | No accidental prod→dev/test DB connection | PASS | `DATABASE_URL` comes from Render's own `fromDatabase` binding in `render.yaml`, not a hardcoded value that could point elsewhere |
| 153 | All production tables managed by migrations | PASS | Single Alembic chain, no manually-created tables found |
| 154 | Alembic has a single head | PASS | `python -m alembic heads` → `0014_consent_log (head)` |
| 155 | A clean DB comes up via all migrations | PASS | `pytest`'s test DB setup runs the full migration chain on every CI/local run (743 passing tests this session all depend on this) |
| 156 | Existing production DB upgrades without data loss | OWNER ACTION REQUIRED | Every migration this session added is additive (per `ERA_PLATFORM_PROGRESS.md`'s stated rule) and upgrade/downgrade-smoke-tested on a throwaway DB — but confirming it against the *actual* production DB's current state needs the owner's own deploy-and-verify, which this session did do for every merged PR via `/health`/`/diag` polling (see §XX) |
| 157 | Foreign keys correctly configured | PASS | `app/database/models.py` — every relationship has an explicit `ForeignKey` |
| 158 | Unique constraints match business rules | PASS | e.g. `PointTransaction.idempotency_key` unique constraint (prevents double-award — see #162) |
| 159 | Nullable fields reviewed | PASS | Reviewed as part of this session's schema changes (e.g. `HomeSnapshot`/`ActivityStats` fields are all required, not accidentally optional) |
| 160 | Critical operations run transactionally | PASS | `get_session()` commits/rolls back the whole request's session as one transaction (`PRODUCTION_READINESS_AUDIT.md` finding #19's fix) |
| 161 | An application cannot be approved twice | PASS | `application_review_service.py::approve_application` — idempotent, returns `already_approved` on a second call, covered by `tests/test_admin_user_card.py::test_approve_application_is_idempotent_and_blocks_rejected` |
| 162 | Points cannot be deducted twice | PASS | `PointTransaction.idempotency_key` unique constraint + `add_points()` requiring a caller-supplied key built from stable identifiers, used consistently across this session's new features (rewards, event activities) |
| 163 | A race between two admins doesn't corrupt data | PASS (via idempotency, not row-locking) | The idempotency-key pattern makes a duplicate concurrent action a no-op rather than a double-effect; **true concurrent-decision race testing was explicitly out of scope** per `frontend/e2e/README.md`'s own "Not covered here" note |
| 164 | Cascade delete/archive behavior defined | PASS | Archive (not hard-delete) is the consistent pattern (`is_archived`, `archived_at`, `archived_by` on `User`; soft-status fields elsewhere) |
| 165 | Integrity audit of existing production data performed | OWNER ACTION REQUIRED | Requires direct production DB access this environment doesn't have |

## XII. Backup / Restore / Disaster Recovery (166–180)

| # | Item | Status | Evidence |
|---|---|---|---|
| 166 | Automated production DB backup configured | PASS (code) / **FAIL (operational)** | `.github/workflows/database-backup.yml` exists and is well-designed, but see the Critical finding above — it has never succeeded because `BACKUP_DATABASE_URL` was never set |
| 167 | Backup runs on a schedule | PASS (schedule fires) | Runs daily at 01:17 UTC per the workflow's cron — it just fails every time, at the same step |
| 168 | Backup retention defined | PASS (defined, moot until backups exist) | 30 days, GitHub Actions artifacts (`docs/BACKUP_AND_RECOVERY.md`) |
| 169 | Backup stored separately from the primary DB | PASS (by design, moot until backups exist) | GitHub Actions artifact storage, separate from Render Postgres |
| 170 | Backup protected from unauthorized access | PASS (by design) | GitHub Actions artifacts are private-repo-scoped |
| 171 | Backup encrypted if required | N/A | Not currently encrypted at rest beyond GitHub's own artifact storage; not flagged as required by any policy in the repo |
| 172 | User file backup configured | N/A | No user files are stored server-side to back up (§X) — Telegram is the file store, outside this app's control |
| 173 | DB restore capability verified | **FAIL** | Cannot verify — there is no successful backup to restore from right now |
| 174 | A real restore test run in an isolated environment | **FAIL** | Same — the workflow's own restore-verification step has never run past the secret-validation step |
| 175 | Data integrity checked after restore | FAIL | Never reached |
| 176 | RPO defined | PASS | ≤24h stated in `docs/BACKUP_AND_RECOVERY.md` — **currently not being met in practice**, since no backup has ever completed |
| 177 | RTO defined | PASS | ≤2h target stated in the same doc |
| 178 | Disaster Recovery Runbook created | PASS | `docs/BACKUP_AND_RECOVERY.md`'s "Восстановление"/"Откат" sections |
| 179 | Scenario for full production DB deletion | PASS (documented) / **currently unusable** | Runbook describes it; it depends on a backup existing, which none currently does |
| 180 | Scenario for production compromise | OWNER ACTION REQUIRED | Not documented — see the High finding above (no incident-response doc at all) |

## XIII. Secrets / Infrastructure / Config (181–195)

| # | Item | Status | Evidence |
|---|---|---|---|
| 181 | Telegram Bot Token absent from Git | PASS | `git grep -InE "BOT_TOKEN\s*=\s*['\"][0-9]{6,}"` finds only obviously-fake test tokens (`tests/test_*.py`) |
| 182 | Database credentials absent from Git | PASS | `.env` gitignored and confirmed not tracked (`git ls-files \| grep '^\.env$'` empty); `render.yaml` uses `fromDatabase`, not a literal string |
| 183 | API secrets absent from frontend bundle | PASS | Frontend only ever holds the Bearer session token issued after auth, never `MINIAPP_AUTH_SECRET`/`BOT_TOKEN` |
| 184 | `.env` excluded from Git | PASS | `.gitignore` line 1: `.env` |
| 185 | `.env.example` has no real secrets | PASS | All secret fields blank; only public-ish invite-link URLs are pre-filled, which is their intended public purpose |
| 186 | Repository history secret-scanned | OWNER ACTION REQUIRED | No `gitleaks`/`trufflehog`-style scan exists in CI or was run ad hoc this session — see High finding #4-adjacent gap noted for CI (§XIV #203) |
| 187 | Previously-compromised secrets rotated | OWNER ACTION REQUIRED | No record of a known compromise in the repo; can't confirm a negative from here |
| 188 | Dev and production use different credentials | PASS | CI/E2E use hardcoded fake `BOT_TOKEN`/`MINIAPP_AUTH_SECRET` (`ci.yml`'s `e2e` job env); production values are Render-generated (`render.yaml`'s `generateValue: true`) |
| 189 | Telegram token rotation procedure defined | PASS | `docs/DEPLOYMENT_RUNBOOK.md`'s "Настройка Telegram" + general secret-rotation note in `PRODUCTION_READINESS_AUDIT.md` finding #12 |
| 190 | DB password rotation procedure defined | PASS | Render-managed Postgres; rotation is a Render Dashboard action, documented as such |
| 191 | Production env vars documented | PASS | `docs/DEPLOYMENT_RUNBOOK.md`'s full table |
| 192 | Critical env vars validated at startup | PASS | `Settings.assert_safe_for_deployment()`; `BOT_TOKEN` length-validated by Pydantic settings |
| 193 | Misconfiguration stops startup safely | PASS | Same guard — refuses to boot rather than run insecurely |
| 194 | HTTPS enabled for production | PASS | Render's default `*.onrender.com` TLS |
| 195 | CORS/trusted hosts restricted to necessary origins | PASS | No `CORSMiddleware` is mounted at all (closed by default, `app/webapp.py` line ~229's comment) — same-origin only, since frontend and API are served by the same process |

## XIV. CI/CD / Supply Chain (196–210)

| # | Item | Status | Evidence |
|---|---|---|---|
| 196 | Every PR runs backend tests | PASS (with caveat) | `.github/workflows/ci.yml`'s `test` job runs on every PR — but see the High finding above: it uses `unittest discover`, which misses 17 test files. This session's own full local `pytest -q` runs (green on every merge) are the actual coverage evidence |
| 197 | Every PR runs frontend tests | PASS | `frontend` job in `ci.yml` (build+typecheck; there is no separate frontend unit-test suite — see #258) |
| 198 | Every PR runs a frontend production build | PASS | `npm run build` in the `frontend` CI job |
| 199 | Every PR runs lint | PASS | `ruff check app --select E9,F` (correctness rules; not a full style lint, by design — `ci.yml`'s own comment) |
| 200 | Every PR runs type checking | PASS (frontend only) | `tsc --noEmit` is part of `npm run build`; **no backend type-checker (mypy/pyright) exists in CI** — this repo doesn't use one at all, so there's nothing to check here for Python |
| 201 | Python dependency audit in CI | PASS | `pip-audit -r requirements.txt --strict`, blocking |
| 202 | npm dependency audit in CI | PASS | `npm audit --audit-level=high`, blocking (PR18b closed the last advisory) |
| 203 | Secret scanning in CI | **FAIL** | No such step exists in any of the three workflow files (`ci.yml`, `tests.yml`, `database-backup.yml`) |
| 204 | Dependency lock files in the repo | PASS | `frontend/package-lock.json` tracked; `requirements.txt` pins versions |
| 205 | Production build is reproducible | PASS | Docker multi-stage build + lock files (`Dockerfile`) |
| 206 | No Critical dependency vulnerabilities | PASS | `pip-audit --strict` and `npm audit --audit-level=high` both clean, run fresh for this document |
| 207 | High vulnerabilities closed or owner-accepted | PASS | None currently open (same audits) |
| 208 | Unused dependencies removed | OWNER ACTION REQUIRED | Not audited this session — would need a dedicated pass (`pip list`/`npm ls` vs. actual imports), not done |
| 209 | GitHub permissions minimized | OWNER ACTION REQUIRED | Org/repo permission settings aren't visible from this session's tooling |
| 210 | Production deploy can't happen from an arbitrary branch | PASS | `render.yaml`'s `autoDeployTrigger: commit` deploys whatever Render's connected branch is (standard Render behavior is the branch selected in the dashboard, normally `main`) — confirming the dashboard setting itself is an owner check, but the repo-side config only ever pushes to `main` via this session's merge flow |

## XV. Logging / Audit / Monitoring (211–225)

| # | Item | Status | Evidence |
|---|---|---|---|
| 211 | Backend errors centrally logged | PASS | Uvicorn's error logger captures unhandled exceptions with full tracebacks, visible in Render's log viewer (per prior `FINAL_PRODUCTION_ACCEPTANCE.md`'s own baseline, still true) |
| 212 | Frontend errors diagnosable | PASS (basic) | Browser console + `AuthErrorScreen`'s error code/detail display; no dedicated frontend error-reporting pipeline beyond that |
| 213 | Logs carry a request/correlation ID | OWNER ACTION REQUIRED | Not implemented — no correlation-ID middleware found in `app/webapp.py` |
| 214 | Tokens not logged | PASS | Spot-checked `app/api/security.py`/`deps.py` — no `logger` call includes the session token |
| 215 | Cookies/session secrets not logged | N/A | No cookies exist (§V #72); session tokens confirmed not logged |
| 216 | Full Telegram `initData` not logged | PASS | Confirmed not logged in `app/api/security.py` |
| 217 | AuditLog records admin actions | PASS | `action="user.approved"`, `"user.rejected"`, `"project.*"`, etc. — `git grep 'action="' app` shows 30 distinct audited action types |
| 218 | AuditLog records role changes | PASS | `action="user.role_changed"` (`rights_block6.py`) |
| 219 | AuditLog records application approve/reject | PASS | `action="user.approved"`/`"user.rejected"` (`application_review_service.py`) |
| 220 | AuditLog records manual points changes | PASS | `action="points.added"` |
| 221 | AuditLog records data deletion/export | **FAIL** | No such action exists — consistent with §VIII #118/#119: there's no deletion/export feature to audit yet |
| 222 | HTTP 5xx monitoring | OWNER ACTION REQUIRED | No external monitoring tool integrated (`PRODUCTION_READINESS_AUDIT.md` finding #14, still open) |
| 223 | DB unavailability monitoring | OWNER ACTION REQUIRED | Same — `/ready` exposes it on-demand, but nothing polls and alerts on it automatically |
| 224 | `/health` and `/ready` monitored | PASS (endpoints exist) / OWNER ACTION REQUIRED (active monitoring) | Both endpoints work and were just confirmed live (`curl` this session); whether Render's own health-check or an external uptime monitor is watching them is an owner-side configuration this session can't see |
| 225 | Owner notified on critical production failure | OWNER ACTION REQUIRED | No alerting integration exists |

## XVI. Performance / Reliability / Autonomy (226–240)

| # | Item | Status | Evidence |
|---|---|---|---|
| 226 | Mini App opens at acceptable speed on mobile internet | PASS (bundle size proxy) | Production JS bundle ≈285KB / 73KB gzipped (`npm run build` output, this session) — small by modern standards; no real network-throttled test performed |
| 227 | No critically heavy frontend bundles | PASS | Same evidence |
| 228 | Large lists aren't loaded whole unnecessarily | PASS | Bounded query limits throughout (§VII #97) |
| 229 | DB queries checked for obvious N+1 | OWNER ACTION REQUIRED | No systematic N+1 audit was performed this session; spot-checks of this session's own new code (`home_service.py`) show single-query aggregation, but a full-codebase pass wasn't done |
| 230 | Necessary DB indexes added | OWNER ACTION REQUIRED | Not audited this session against real query patterns/`EXPLAIN` output |
| 231 | Slow Telegram API doesn't block the whole system | PASS | `notification_service.py::broadcast_detailed` already handles bounded concurrency + retry (`PRODUCTION_READINESS_AUDIT.md`'s pre-existing-good list) |
| 232 | An external service can't hold a request forever | PASS (reasonably) | aiogram/httpx client defaults apply timeouts; no evidence of an unbounded external call found |
| 233 | Timeouts configured | PASS | Same |
| 234 | Safe retries configured | PASS | `broadcast_detailed`'s exponential-backoff retry, transient-vs-permanent error split |
| 235 | Retries don't create duplicate operations | PASS | Idempotency-key pattern (§XI #162) makes retried mutations safe |
| 236 | Scheduler survives an app restart | PASS | No in-memory-only scheduled state found; FSM state lives in Redis, not process memory |
| 237 | Pending delivery isn't counted as delivered | PASS | `notification_service.py` distinguishes delivered vs. failed explicitly |
| 238 | Bot automatically returns to a working state after restart | PASS | Webhook re-registered at startup (`app/webapp.py::lifespan`), no manual step |
| 239 | No manual developer intervention needed after a normal deploy/restart | PASS | Same — migrations run automatically (`Dockerfile`'s `CMD`), webhook re-set automatically |
| 240 | 24–48h unattended autonomous operation scenario tested | **FAIL** | Not tested this session — this environment's session length doesn't span that, and no owner-run soak test is on record |

## XVII. Bot / Chat / Notifications / Broadcast (241–255)

| # | Item | Status | Evidence |
|---|---|---|---|
| 241 | Unregistered user cannot write in the general chat | PASS (code-level) | `chat_access_service.py`'s `moderation_gate`; re-verified PR18c |
| 242 | Incomplete registration doesn't grant write access | PASS (code-level) | Same |
| 243 | Pending registration doesn't grant write access | PASS (code-level) | Same |
| 244 | Admin approval automatically opens access | PASS (code-level) | `sync_user_chat_access`, called from the approval path |
| 245 | Rejected registration keeps the restriction | PASS (code-level) | Same service |
| 246 | Re-joining doesn't bypass restrictions | PASS (code-level) | `handle_chat_join_request` re-checks status every time, not just on first join |
| 247 | Manual ban takes priority over approval | PASS (code-level) | `is_blocked` checked ahead of `application_status` in `chat_access_service.py`'s access logic |
| 248 | Greetings don't duplicate | PASS (code-level) | `welcome_members` logic reviewed in `PRODUCTION_READINESS_AUDIT.md`'s baseline, unchanged since |
| 249 | Bot doesn't send greetings to unrelated chats | PASS (code-level) | Chat IDs are config-scoped (`chat_key_for_id`), not wildcard |
| 250 | General broadcast actually reaches the general chat | PASS (code-level) | `broadcast_detailed` targets configured chat IDs |
| 251 | Personal broadcast doesn't leak publicly | PASS (code-level) | Personal vs. chat broadcasts are distinct code paths, not a shared "audience" flag that could be misconfigured |
| 252 | Combined broadcast doesn't create duplicates | PASS (code-level) | Recipient deduplication is an explicit, named feature of `broadcast_detailed` |
| 253 | Notification deep link opens the right Mini App object | PASS (tab-level) / Backlog (item-level) | Same caveat as §II #24 — tab-level works and is tested, per-notification item-level linking wasn't reached this session |
| 254 | Failed delivery retried safely after a Telegram API failure | PASS (code-level) | `broadcast_detailed`'s retry logic |
| 255 | Delivery success/failure statistics tracked | PASS (code-level) | Same function returns detailed stats |

*Every item in this section is marked PASS at the code level, re-verified by reading the code in PR18c (no code change needed) — none of it was clicked through live in this pass, consistent with High finding #3 above.*

## XVIII. QA / E2E / Device Testing (256–270)

| # | Item | Status | Evidence |
|---|---|---|---|
| 256 | Full backend pytest green | PASS (with the CI caveat from the High finding) | `pytest -q` → 743 passed, run repeatedly this session, most recently immediately before merging PR 38 |
| 257 | Existing unittest suite green | PASS (narrower than #256) | `python -m unittest discover -s tests` passes for the files it actually collects — see High finding #4 for what it misses |
| 258 | Frontend test suite green | N/A | No dedicated frontend unit-test framework (Jest/Vitest) exists in this repo — type-checking (`tsc`) + build + E2E are the frontend's actual test layers, both green |
| 259 | Production frontend build green | PASS | `npm run build` this session, clean |
| 260 | E2E Participant flow green | PASS | `participant.spec.ts` + `deep_links.spec.ts` + `event_cancel_confirmation.spec.ts`, CI `e2e` job green on every PR this session |
| 261 | E2E Leader flow green | PASS | `leader.spec.ts`, `event_activities.spec.ts` |
| 262 | E2E Admin flow green | PASS | `admin.spec.ts`, `admin_people.spec.ts`, `admin_catalog.spec.ts`, `admin_offices.spec.ts`, `pending_sync.spec.ts`, `rewards.spec.ts`, `auctions.spec.ts`, `surveys.spec.ts` |
| 263 | New user `/start` → approved account verified | PASS (E2E) | `pending_sync.spec.ts` + `admin.spec.ts` cover the approval half; registration-form submission itself isn't E2E-covered (Bot-only FSM, outside Playwright's reach) |
| 264 | Full project/task flow verified | PASS (E2E) | `participant.spec.ts` (event registration), `leader.spec.ts` (open task creation) — full project-workspace lifecycle isn't one single E2E spec, though `ProjectWorkspace.tsx` itself is the most-built screen in the app |
| 265 | Full opportunity/points flow verified | PASS (E2E) | `rewards.spec.ts`, `auctions.spec.ts` |
| 266 | Portfolio upload/view/delete flow verified | **FAIL** | Explicitly disclosed as not covered by `frontend/e2e/README.md`'s own "Not covered here" note — uploads are Bot-only FSM (§X), can't be exercised by Playwright |
| 267 | Telegram Desktop checked | OWNER ACTION REQUIRED | No Telegram client access in this environment |
| 268 | At least one real mobile Telegram client checked | OWNER ACTION REQUIRED | Same |
| 269 | Widths 320/360/390/430/768px checked | FAIL | E2E fixed at a single 390×844 viewport (`playwright.config.ts`); no multi-width pass performed |
| 270 | Final regression after the last production merge | PASS | `pytest -q` (743 passed) run immediately before merging PR 38, the most recent merge to `main` |

## XIX. Incident Response / Ownership / Business Continuity (271–285)

| # | Item | Status | Evidence |
|---|---|---|---|
| 271 | Technical production owner assigned | OWNER ACTION REQUIRED | No named individual anywhere in the repo |
| 272 | BotFather owner assigned | OWNER ACTION REQUIRED | Not documented |
| 273 | Hosting/Render owner assigned | OWNER ACTION REQUIRED | Not documented |
| 274 | Production DB owner assigned | OWNER ACTION REQUIRED | Not documented |
| 275 | Critical accounts not single-owner without recovery | OWNER ACTION REQUIRED | `render.yaml`'s `ADMIN_IDS` is one Telegram ID; no evidence of a second admin or recovery plan anywhere |
| 276 | MFA enabled where supported | OWNER ACTION REQUIRED | Can't be verified or configured from this environment |
| 277 | Recovery codes safely stored | OWNER ACTION REQUIRED | Same |
| 278 | Document listing all production services + owners exists | FAIL | No such document exists in `docs/` |
| 279 | Incident Response Runbook exists | **FAIL** | Confirmed — `find docs -iname "*incident*"` returns nothing |
| 280 | Scenario for Telegram Bot Token leak | FAIL | Not documented (rotation procedure exists, §XIII #189, but not an incident playbook) |
| 281 | Scenario for admin account compromise | FAIL | Not documented |
| 282 | Scenario for production DB leak | FAIL | Not documented |
| 283 | Scenario for hosting provider unavailability | FAIL | Not documented beyond the generic rollback steps in `DEPLOYMENT_RUNBOOK.md` |
| 284 | Participant-notification procedure for serious incidents | OWNER ACTION REQUIRED | Depends on the legal/organizational decisions in §IX, not yet made |
| 285 | Post-incident root-cause review process defined | FAIL | Not defined |

## XX. Final Production Release (286–300)

| # | Item | Status | Evidence |
|---|---|---|---|
| 286 | Exact release commit SHA recorded | PASS | `bb19003` |
| 287 | GitHub `main` clean and synced | PASS | `git status --short --branch` → clean, up to date with `origin/main`, at this document's writing |
| 288 | All production migrations applied | PASS | Single Alembic head; migrations run automatically at container start (`Dockerfile` `CMD`) |
| 289 | `/health` shows the current release | PASS | `curl https://era-telegram-bot.onrender.com/health` → `{"status":"ok","version":"2.1.0","commit":"bb19003"}` |
| 290 | `/ready` confirms backend+DB readiness | PASS | `curl .../ready` → `{"status":"ready"}` |
| 291 | Telegram `getMe` confirms the correct bot | PASS | Via `/diag` (computed from a real `getMe()` at boot) |
| 292 | `getWebhookInfo` confirms the correct production webhook | PASS | Via `/diag`'s `webhook_host` |
| 293 | `getChatMenuButton` confirms the current Mini App | PASS | Via `/diag`'s `menu_button_type`/`menu_button_verified` |
| 294 | The real Mini App opens from the production bot | OWNER ACTION REQUIRED | Needs a live Telegram client click-through (High finding #3) |
| 295 | Real registration → admin approval → chat access chain verified | PASS (E2E) / OWNER ACTION REQUIRED (live) | `pending_sync.spec.ts`/`admin.spec.ts` prove it against a real backend; not clicked through live in real Telegram |
| 296 | Real Participant → Project → Task → Portfolio chain verified | PASS (E2E, partial) / FAIL (portfolio leg) | Project/task covered by E2E; portfolio upload isn't (§XVIII #266) |
| 297 | Real Opportunity → Approval → Points chain verified | PASS (E2E) | `rewards.spec.ts` |
| 298 | Real Leader Mode and Admin Mode verified after deploy | PASS (E2E, post-merge CI) / OWNER ACTION REQUIRED (live) | E2E green on the exact commits deployed; not live-clicked in production Telegram |
| 299 | Backup created before final release, restore verified | **FAIL** | Directly follows from the Critical finding — no backup has ever succeeded |
| 300 | This document issued with a stated verdict | PASS | This document; verdict: **NOT READY FOR LAUNCH** |

---

## What would need to change to reach READY FOR LAUNCH

In priority order:

1. **Owner sets `BACKUP_DATABASE_URL`, manually triggers `database-backup.yml`
   once, confirms a green run.** Closes the one Critical item. Everything in
   §XII downstream of it (restore verification, RPO/RTO actually being met)
   becomes checkable immediately after.
2. **Owner (with a lawyer where the checklist itself says one is needed)
   resolves §IX**: legal entity, jurisdiction, final Privacy Policy text,
   consent-version content, minors policy, photo/video publication basis,
   written sign-off. This closes High #1 and most of §VIII's remaining
   FAILs (retention, export, deletion — those follow naturally once the
   legal basis is settled).
3. **A named second owner + MFA/recovery codes for Render/GitHub/BotFather,
   plus a short incident-response doc** (even a one-page version covering
   the four scenarios in §XIX). Closes High #2.
4. **The owner (or a future session with real Telegram access) clicks
   through the bot and Mini App on an actual device once**, confirming
   §XVIII #267–269 and §XX #294–298's live half. Closes High #3.
5. **Land `task_6f10a296`** (already spawned, already started by the owner
   in a separate session) — switches CI to `pytest`, closing the gap behind
   High #4.
6. Lower-priority but real: add a CI secret-scanning step (§XIV #203), an
   E2E spec (or at least a manual owner check) for portfolio upload/view/
   delete (§XVIII #266), and per-notification deep links (§II #24/§XVII
   #253) — none of these are stop-ship on their own, but each closes a
   named gap rather than leaving it silently unaddressed.

Once 1–5 are done, re-run this checklist's automated-evidence items fresh
(most of §I–§VIII, §X–§XI, §XIII–§XVIII, §XX are already re-runnable
commands, not new work) and issue an updated verdict. Item 6 can follow in
normal PR cadence after launch — it doesn't block it.
