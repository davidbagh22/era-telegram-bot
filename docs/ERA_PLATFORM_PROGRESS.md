# ERA Platform — progress

Single source of truth for the Bot + Mini App platform build-out. Read this
file first in every new session, then `git status` / `git log -1`, then only
the files touched by the current block. Do not re-audit the whole repo.

## Baseline

- Current `main` commit: `d983849385b5a14dd271c9ec4d7635ec2d2e7e66`
  (progress doc update after PR #113 merge).
- PR #113 merge commit:
  `5218911a35f5f6b5e2d1cff23f8e51d641ca3375`.
- Previous: `edc173035aec2ee6235af4441f0bc926009c1168` (PR #112 merge),
  `48212168f316b6b43b4f14aea913648693c12954` (PR #111 merge),
  `b3a4e2a521158da92afbc10f379535081c8f6c0a` (PR #110 hotfix),
  `905c0acf61be80108d63b78820972d9d08e1677e` (PR #109 merge),
  `1a040973a9782264e01f940998ad4b34c6a0c9a5` (PR #108 merge),
  `36098e985e407f806f7a0134dafc36152a9f71a8` (PR #107 merge, pre-platform
  baseline).
- Bot Hardening phase (v2) is complete: 209 tests passing, single Alembic
  head (`0011_pending_chat_join_requests`), see `docs/ERA_V2_ARCHITECTURE.md`
  and `docs/ERA_V2_AUDIT.md` for the domain model this platform builds on.
- Render service name: `era-telegram-bot` (frankfurt, free plan). Exact
  public hostname not recorded in the repo — could not verify `/health`
  against the base commit from this environment; owner should confirm
  Render is on `36098e9` before any migration-bearing PR merges.

## Architecture decisions

- Mini App auth is a thin layer on top of existing tables: no new `User`
  entity, no parallel session store. Telegram `initData` is HMAC-verified
  server-side (`app/api/security.py`), then a short-lived signed session
  token (HMAC, 1h TTL, no external JWT dependency) is handed to the
  frontend. The token only carries `telegram_id` + expiry; every request
  re-reads the `User` row, so role/permission/block changes take effect
  immediately.
- API lives under `app/api/`, versioned at `/api/v1/*`, mounted onto the
  existing single FastAPI `app` in `app/webapp.py` (no second process, no
  second deployment).
- API handlers stay thin and call the same repositories/services the bot
  handlers use (`app/repositories/*`, `app/services/*`). No business logic
  is duplicated between Telegram handlers and API routes.
- Permissions are re-checked on the backend using the existing
  `app/services/authorization_service.py` helpers (`is_full_admin`,
  `active_permissions`, `PRIVILEGED_ROLES`) — the same source of truth the
  bot's admin/leader panels already use.
- Frontend: React + TypeScript + Vite, no Next.js/Redux/separate Node
  backend, per `frontend/` (see PR 1 section below for structure).
- Bot menu is only ever additive in this phase: `main_menu()` gained an
  optional `miniapp_url` kwarg that appends a `🔥 Открыть ЭРА` WebApp button
  when `MINIAPP_URL` is configured; every existing button, callback and
  test contract is unchanged.

## Final product decision for Projects

- Mini App is the primary project-management interface once functional
  parity is reached. Project creation, draft saving, editing, review
  submission, revision handling, status management, Project Workspace,
  team, roles, applications, tasks, milestones, events, materials,
  contribution, reports, analytics, admin moderation and curator assignment
  belong in the Mini App.
- Telegram Bot must not keep growing into a second project-management
  workspace. After parity, it keeps project notifications, object-specific
  deep links into the Mini App, simple confirmations that are genuinely
  faster in Telegram, and file/video/document/report uploads where Telegram
  is the better upload surface.
- In PR 5, the old Telegram project FSM is **not removed**. Project
  Workspace and Admin Project Management are not complete yet, so the FSM
  remains a legacy fallback. Do not add new project-management features to
  that FSM; new project work is Mini-App-first and should reuse shared
  services.
- A separate Project Bot Cleanup PR comes only after Project Workspace,
  Leader Mode and Admin Project Moderation reach parity. That PR should
  replace project create/manage buttons with WebApp/deep-link buttons, keep
  notifications/uploads, migrate regression coverage to API/service/Mini
  App flows, and only then remove the legacy FSM.
- Project notifications must deep-link to the exact object: a returned
  project opens that project, a team application opens that application,
  and an admin moderation notice opens the exact project in Admin Mode.

## Mini App design decision

- Visual direction: "energy turning into growth" — official, modern,
  movement-oriented, strong enough to show partners. Avoid a stock Telegram
  WebView, Bootstrap admin look, government portal feel, crypto aesthetics,
  childish game styling, random purple UI, and repetitive white-card grids.
- Brand colors are fixed in `frontend/src/theme/tokens.css`: ERA Red
  `#E52B24`, ERA Violet `#742CC4`, ERA Magenta `#BE268F`, main gradient
  `linear-gradient(135deg, #742CC4 0%, #B529A6 48%, #E52B24 100%)`,
  background `#F8F6F9`, surface `#FFFFFF`, text `#1B1720`, secondary text
  `#756E7A`, border `#EAE5ED`, success `#16845B`, warning `#C77A00`,
  error `#D92D20`.
- Red is for primary CTAs, active states and urgency. Violet is for growth,
  level and leader-oriented functions. Magenta is rare and used as a brand
  transition/accent. The gradient is reserved for splash/hero/journey/pass
  and major achievements, not for every button or card.
- Typography remains Unbounded for short headers, levels, branded labels and
  large numbers; Golos Text for UI, forms, descriptions, tables and buttons.
  Do not use Unbounded for long text.
- UI is mobile-first, 8px-grid based, with 16px horizontal padding, 24px
  major section spacing, 44px minimum touch targets, soft 18-22px cards,
  safe-area handling, and loading/empty/error/retry/success states.

## Env vars owner must set (not guessed, not hardcoded)

- `MINIAPP_AUTH_SECRET` — random secret used to sign Mini App session
  tokens. **This is the only var required to turn the feature on.** Until
  it is set, `Settings.effective_miniapp_url` stays empty on purpose (see
  PR 1b below), so the bot menu shows no button and
  `/api/v1/miniapp/auth` returns 500 `miniapp_auth_not_configured` if
  called directly — no broken button is ever shown to users.
  `render.yaml` declares it with `generateValue: true` (same pattern as
  `WEBHOOK_SECRET`), but that only takes effect on a Render **Blueprint
  sync** — a normal git-push deploy of an already-existing service does
  not automatically add new blueprint env vars. Owner should check the
  Render dashboard → Environment tab for this service and either sync the
  blueprint or add `MINIAPP_AUTH_SECRET` manually if it isn't there after
  this PR deploys.
- `MINIAPP_URL` — only needed if the Mini App frontend is hosted
  separately from this backend. By default (PR 1b) the frontend is built
  into this same Docker image and served at `<PUBLIC_BASE_URL>/app/`, so
  this can stay blank.
- `BOT_USERNAME` — used later for bot deep-link helpers (PR building
  `miniapp_link()` / `task_submit:<context>` helpers); not required yet.
- `PUBLIC_BASE_URL` — already existed before this platform work; unchanged.

## PR log

### PR 1 — ERA Platform foundation (merged)

- Branch: `era-platform-pr1-foundation`. PR: [#108](https://github.com/davidbagh22/era-telegram-bot/pull/108).
  Merge commit: `1a040973a9782264e01f940998ad4b34c6a0c9a5`. Both CI checks
  (Tests, Bot checks) green before merge.
- Full suite after merge: 239 passed via `pytest -q` (209 pre-existing + 30
  new, 0 regressions), 156 passed via `python -m unittest discover -s tests`
  (the exact command CI runs).
- Render deploy of this commit not verified from this environment (no
  hardcoded service hostname in the repo) — confirm `/health` reports
  commit `1a04097` before relying on the Mini App endpoints in production.

- `docs/ERA_PLATFORM_PROGRESS.md` created (this file).
- `app/api/security.py` — Telegram `initData` HMAC verification +
  HMAC-signed session token issue/verify (no new dependency).
- `app/api/deps.py` — `get_settings`, `get_session`, `get_current_user`
  FastAPI dependencies.
- `app/api/v1/auth.py` — `POST /api/v1/miniapp/auth`.
- `app/api/v1/me.py` — `GET /api/v1/me`.
- `app/api/v1/router.py` — aggregates `/api/v1/*` routers.
- `app/webapp.py` — mounts the v1 API router on the existing FastAPI app.
- `app/config.py` — new settings: `miniapp_url`, `bot_username`,
  `miniapp_auth_secret` (all default `""`, fully backward compatible).
- `app/keyboards/participant.py` — `main_menu()` gained optional
  `miniapp_url` kwarg (additive, default `""`, no behavior change when unset).
- Call sites passing `settings.miniapp_url` into `main_menu()`:
  `app/handlers/start.py`, `app/handlers/registration.py`,
  `app/handlers/admin/panel.py`, `app/handlers/admin/rights_block6.py`,
  `app/handlers/admin/approval_bonus_fix.py`.
- `frontend/` — React + TypeScript + Vite shell: Telegram WebApp SDK bridge,
  API client that performs the `initData` handshake, route guard
  scaffolding for User/Leader/Admin layouts (placeholder screens only).
- Tests: `tests/test_miniapp_security.py` (initData verification, token
  issue/verify, tamper/expiry), `tests/test_miniapp_auth_api.py` (auth +
  `/me` endpoints via `TestClient`, dependency-overridden — no real Postgres
  needed), `tests/test_participant_menu_miniapp_button.py` (menu stays
  backward compatible with and without `MINIAPP_URL`).
- New dependency: `httpx` (required by `fastapi.testclient.TestClient`),
  added to `requirements.txt`.
- No migrations in this PR — no new tables needed for auth foundation.

**Known limitations after PR 1:** no Home/Activity/Projects screens yet
(frontend shell only renders a placeholder + auth handshake status); no
deep-link helpers yet; no product analytics events yet.

### PR 1b — bundle the Mini App into the existing deploy (merged)

Branch: `era-platform-pr1b-deploy-miniapp`. PR:
[#109](https://github.com/davidbagh22/era-telegram-bot/pull/109). Merge
commit: `905c0acf61be80108d63b78820972d9d08e1677e`. Both CI checks green
before merge.

The user asked for the change to actually be live on Render, not just
merged as code. PR 1 built the frontend but never deployed it anywhere,
so this follow-up closes that gap without adding a second service:

- `Dockerfile` — new `node:20-alpine` build stage runs `npm ci && npm run
  build` for `frontend/`, then the final Python stage copies
  `frontend/dist` into the image. One Docker image, one Render service,
  still.
- `app/webapp.py` — `_mount_frontend()` serves `frontend/dist` at `/app`
  via `StaticFiles(html=True)` when the directory exists. It **must not
  raise** when the directory is missing (local dev / CI never run `npm
  run build`), so it logs a warning and no-ops instead — verified by
  `tests/test_webapp_frontend_mount.py`.
- `app/config.py` — `Settings.effective_miniapp_url` now drives the
  button: falls back to `<PUBLIC_BASE_URL>/app/` when `MINIAPP_URL` is
  blank, and **stays empty until `MINIAPP_AUTH_SECRET` is set**, even if a
  base URL exists — this was a deliberate fix during review: without the
  gate, the button would have appeared as soon as `PUBLIC_BASE_URL` was
  configured (already true in production today), before the auth secret
  existed, shipping a visibly broken button. Covered by
  `tests/test_effective_miniapp_url.py`.
- `render.yaml` — added `MINIAPP_AUTH_SECRET` with `generateValue: true`
  (see the "Env vars owner must set" section above for the Blueprint-sync
  caveat).
- Verified locally (Docker itself is not available in this environment):
  `npm ci` from the committed lockfile succeeds, `npm run build` produces
  `dist/`, and a real `TestClient` request against `app.webapp.app` serves
  `/app/` (200, real `index.html`) side by side with the existing
  `/health` (200, unchanged). Full suite: 246 passed, 0 regressions.

### Hotfix — .dockerignore blocked the miniapp-build stage (merged)

PR [#110](https://github.com/davidbagh22/era-telegram-bot/pull/110), merge
commit `b3a4e2a521158da92afbc10f379535081c8f6c0a`. The Render build for PR
1b failed: `.dockerignore` had a pre-existing blanket `frontend` entry
(predates this platform work) that excluded the whole directory from the
Docker build context, so the new `miniapp-build` stage's
`COPY frontend/ ./` had nothing to copy —
`"/frontend/package.json": not found`. Fixed by narrowing the exclusion to
`frontend/node_modules` and `frontend/dist` only. Added
`tests/test_dockerignore_allows_frontend_source.py` as a regression guard,
since the Python test suite otherwise can't catch a Docker-build-context
bug like this. **Docker itself is not available in this environment — the
actual Render build was never re-verified end-to-end from here.** Confirm
the next Render deploy succeeds before assuming the Mini App is really
live.

### PR 2 — design system, bottom navigation, Home, Growth Level (merged)

Branch: `era-platform-pr2-home-growth`. PR:
[#111](https://github.com/davidbagh22/era-telegram-bot/pull/111). Merge
commit: `48212168f316b6b43b4f14aea913648693c12954`. Both CI checks green
before merge.

- **Growth Level** (`app/services/growth_service.py`) is computed, not a new
  column: `participation_status` (an existing 6-tier field already
  maintained by admin/leader flows) maps to the 3-tier
  Участник/Активный/Лидер shown on Home via a plain dict
  (`GROWTH_LEVEL_BY_PARTICIPATION_STATUS`) — that dict is the "configurable
  criteria" point mentioned in the brief; no migration needed. Promotion to
  "Лидер" still requires a human to move `participation_status` via the
  existing flows — this module only computes the display tier, it does not
  add a new approval workflow.
- **Home aggregation** (`app/services/home_service.py`, `GET /api/v1/home`)
  computes, from real data only: points balance (sum of `PointTransaction`),
  nearest registered upcoming event, active/overdue assigned task, an
  authored project needing action (draft or needs-revision), up to 3
  not-yet-applied active `PartnerInitiative` rows (the existing "partner
  offers" tables — this **is** the Opportunities domain model, no new table
  needed), and a rule-based `next_step` following the brief's priority
  order (task → event → project → growth nudge → opportunity). Deliberately
  **not** built: "attention items" (would just restate next_step for a
  plain participant) and "recent activity" (needs the `UserActivityEvent`
  model planned for the Analytics PR) — left out rather than faked.
- **Frontend**: `frontend/src/components/` gained `Card`, `ProgressBar`,
  `MetricCard`, `StatusBadge`, `EmptyState`, and a hand-drawn outline icon
  set (`icons.tsx`, no icon-library dependency, no emoji). `BottomNavigation`
  drives 5 tabs (Главная/Активность/Проекты/Возможности/Профиль) via plain
  React state in `App.tsx` — no router added yet; one is worth introducing
  once deep links (section 15 of the brief) need real URLs. Only Home has
  real content; the other 4 tabs render a "coming soon" placeholder.
  `HomeScreen` replaces `HomePlaceholder` and consumes `GET /api/v1/home`
  with loading/error/empty states per section.
- Verified in a real browser against a temporary local mock HTTP server
  (not committed) standing in for the backend, since spinning up
  Postgres/Redis/a real bot token wasn't practical here: auth handshake,
  full Home render (all 6 sections + empty states), and bottom-nav tab
  switching all confirmed working end-to-end.
- Tests: `tests/test_growth_service.py` (pure mapping logic),
  `tests/test_home_service.py` (integration tests against a real
  `sqlite+aiosqlite` in-memory DB — priority ordering, past-event exclusion,
  applied/expired opportunity exclusion, points summation),
  `tests/test_home_api.py` (route auth + response shape via `TestClient`).
  New dependency: `aiosqlite` (async SQLite driver, test-only in practice),
  added to `requirements.txt`.
- **Known gap:** no frontend test runner is configured yet (verification is
  `tsc` + `vite build` + manual browser check, same as PR 1) — worth adding
  when component logic gets non-trivial enough to justify it.

### PR 3 — Activity (Events, Tasks, Calendar, History) + Bot submission handoff (merged)

Branch: `era-platform-pr3-activity`. PR:
[#112](https://github.com/davidbagh22/era-telegram-bot/pull/112). Merge
commit: `edc173035aec2ee6235af4441f0bc926009c1168`. Both CI checks green
before merge.

- **Refactored two existing bot handlers into shared services before
  building the API on top of them** (this is the "extract *Service before
  write-enabled API" step from section 16 of the brief):
  - `app/services/event_registration_service.py` gained
    `can_change_registration_plans()` / `mark_not_coming()`, moved out of
    `app/handlers/participant/event_plans_changed.py`'s private
    `_can_change_plans()`.
  - `app/services/task_service.py` is new: `list_for_user`, `can_view`,
    `can_submit`, `is_open_public_task`, `claim`, etc., moved out of
    `app/handlers/participant/task_block2.py`'s private helpers (`_can_view`,
    `_can_submit`, `_tasks_for_user`, the inline `task:join` logic, ...).
  - Both refactors are behavior-preserving — full suite (267 tests at that
    point) still passed unchanged before any new feature code was added.
    One existing test (`test_participant_tasks_cabinet.py`) asserted on a
    literal private function name via `inspect.getsource`; updated it to
    assert on the new shared-service call instead, since the underlying
    guarantee (audience filtering happens) is unchanged, only relocated.
- `app/services/activity_service.py` — `list_events` (all/for_me/mine/past),
  `list_tasks` (available/mine/review/completed), `calendar_items` (events +
  task deadlines, sorted, horizon-limited), `history_entries` (attended
  events, completed tasks, verified `PortfolioItem`s only — unverified ones
  are deliberately excluded per the brief's "don't show unverified data as
  confirmed" rule, points transactions).
  - `for_me` is an alias of `all`: `Event.access_type` exists on the model
    but nothing reads it anywhere in the bot today, so there is no real
    targeting rule to reuse yet — faking one would violate "no mock
    production data." Real personalization is future work.
  - Opportunities reuse the existing `PartnerInitiative` /
    `PartnerOfferApplication` tables (same as Home in PR 2) — still no new
    model for this domain.
- `app/api/v1/events.py` (`GET /events`, `GET /events/{id}`,
  `POST /events/{id}/register`, `POST /events/{id}/cancel`),
  `app/api/v1/tasks.py` (`GET /tasks`, `GET /tasks/{id}`,
  `POST /tasks/{id}/claim`), `app/api/v1/activity.py`
  (`GET /activity/calendar`, `GET /activity/history`) — all thin, all
  delegating to the services above.
- **Bot submission handoff** (section 15): `app/utils/deep_links.py` builds
  `https://t.me/<bot_username>?start=task_submit_<id>`.
  `app/handlers/start.py` parses that payload (`CommandObject.args`) and, if
  `task_service.can_submit()` allows it, jumps straight into the existing
  `TaskSubmissionStates.result` FSM instead of showing the home menu —
  uploads still only ever happen inside the Bot. Not cryptographically
  signed: the same `can_submit()` permission check that already gates the
  in-bot "📤 Отправить результат" button gates this too, so an unsigned task
  id cannot grant access beyond what that check allows. `TaskOut` includes
  `submit_deep_link` (null unless `can_submit` and `BOT_USERNAME` is set) so
  the frontend never needs its own copy of the bot username.
- Frontend: `ActivityScreen` with 4 pill-tab sub-sections
  (События/Задачи/Календарь/История, `frontend/src/screens/activity/`),
  register/cancel/claim actions wired to the new endpoints, task submission
  is a plain link to the bot deep link (opens Telegram). New generic
  `useAsync` hook and `PillTabs` component reused across all 4 tabs.
  Verified in a real browser against an extended local mock server (not
  committed): all 4 tabs render, register/cancel/claim buttons appear per
  the correct rules, the deep link renders as an actual `https://t.me/...`
  href.
- **Found and fixed a real bug in my own earlier test helpers while writing
  new ones**: `app.dependency_overrides[get_session] = lambda: iter([...])`
  (used in `test_home_api.py` and `test_miniapp_auth_api.py` from PR 2) is
  wrong for FastAPI's async-generator dependency protocol — it happened to
  work there only because those particular routes never actually touched
  `session`. The new Events/Tasks route tests do, which surfaced it
  immediately (`AttributeError: 'list_iterator' object has no attribute
  'get'`). Fixed all three test files to override with a proper
  `async def _session_override(): yield session`.
- Tests: `tests/test_activity_service.py` (integration, real
  `sqlite+aiosqlite`), `tests/test_activity_api.py` (routes, dependency
  overrides), `tests/test_task_submit_deep_link.py` (deep link parsing +
  the handoff predicate). Full suite: 302 passed via `pytest -q`, 219 via
  `python -m unittest discover -s tests` (matches CI), 0 regressions.
- No migrations — no new tables needed.

**Known limitation:** "decline a task after joining" (section 7.2's
"отказаться по правилам") is not implemented — no such rule exists
anywhere in the bot today (only leaders can reject a participant, via
`app/handlers/leader/open_tasks.py`), so there is no existing business
rule to reuse and none was invented here.

### PR 4 — Projects read/create/edit + workflow (merged)

Branch: `era-platform-pr4-projects`. PR:
[#113](https://github.com/davidbagh22/era-telegram-bot/pull/113). Merge
commit: `5218911a35f5f6b5e2d1cff23f8e51d641ca3375`. Both CI checks green
before merge.

- Discovered `app/services/project_service.py::create_project` is dead code
  — nothing calls it. The real project-creation flow
  (`app/handlers/participant/projects.py::project_start` +
  `project_answer`) builds a `Project` directly and fills it in through an
  18-question guided FSM wizard with AI-hint prompts
  (`app/services/project_builder.py::PROJECT_QUESTIONS`). Left the dead
  code alone — unrelated to this block, not blocking anything.
- **Did not rebuild the 18-step AI-hint wizard in the Mini App.** That is a
  real, separate UI investment (per-question hints, block grouping) and
  deserves its own focused work rather than a rushed clone bolted onto this
  PR. Instead: `app/services/project_workflow_service.py` exposes the same
  question set as a single scrollable form (all 16 free-text questions;
  `proposed_date`/`proposed_time` excluded — the Bot wizard parses those
  into typed `Project` columns, the Mini App's `update_answers()` only
  writes plain strings into `form_data`, so mixing the two would silently
  produce a worse result than just leaving those two Bot-only for now).
  `GET /api/v1/projects/questions` serves the question copy from
  `PROJECT_QUESTIONS` directly so the frontend never hand-maintains a
  second copy of the wording.
- Extracted shared logic from `app/handlers/participant/projects_block5.py`
  into `project_workflow_service.py` before adding the API (same pattern as
  PR 3): `can_edit` / `can_submit_for_review` / `can_delete` gates,
  `submit_for_review()` (status transition + document generation + audit,
  returns the document text), `cancel_project()`. The Bot handler's
  Telegram-specific notification broadcast to admins/leaders stays in the
  Bot handler — only the state transition moved. Full suite passed
  unchanged before any new feature code was added.
- New `GET/POST/PATCH /api/v1/projects*` routes. Four scopes:
  `mine` (all of the author's non-cancelled projects — was already how the
  Bot works), `proposals` and `completed` (subsets of `mine`, split out for
  the UI tabs the brief asks for), and `open` — **genuinely new**: a
  directory of all authors' `approved`/`in_progress` projects. No
  participant-facing feature like this existed before (the Bot only ever
  shows a participant their own projects); it's a real query with no
  fabricated data, and PR 5's "find a team" workspace needs something to
  browse.
- Submitting a project via the Mini App triggers the **same** admin/leader
  Telegram notification the Bot's submit flow sends — not a second, silent
  path — because the FastAPI process and the Bot share one `aiogram.Bot`
  instance (`app.api.deps.get_bot()` reads `request.app.state.bot`, which
  the shared lifespan already sets up). Falls back to skipping the
  notification (never crashing) when no bot is attached, e.g. in tests.
- Frontend: `ProjectsScreen` (list with 4 scope tabs + inline "create
  draft" box) and `ProjectDetail` (status, admin comment, the 16-field edit
  form when `can_edit`, submit/cancel actions gated by the same
  `can_submit`/`can_delete` flags the backend computes). Verified in a
  browser against an extended local mock server: list renders, detail
  loads with prefilled answers, submitting flips status and correctly
  hides the now-inapplicable edit/submit controls.
- Tests: `tests/test_project_workflow_service.py` (integration, real
  `sqlite+aiosqlite` — scope filtering, edit/submit/delete gates, document
  reuse-vs-regenerate), `tests/test_projects_api.py` (routes, including a
  regression test that `GET /projects/questions` isn't shadowed by
  `GET /projects/{project_id}` — a real FastAPI route-ordering trap).
  Full suite: 325 passed via `pytest -q`, 242 via
  `python -m unittest discover -s tests` (matches CI), 0 regressions.
- No migrations — no new tables needed.

**Known limitations:** no AI-hint feature in the Mini App edit form (Bot
wizard only, see above); `proposed_date`/`proposed_time` are not editable
from the Mini App yet for the same reason.

**Next block:** PR 5 — Project Workspace (ProjectMember, ProjectRole,
Team, Milestones, contribution) — this is the first PR expected to need a
migration.

### PR 5 — Project Workspace foundation (in progress)

Branch: `pr5-project-workspace-foundation`. PR: pending.

Scope of this foundation block:

- Product decision fixed: Mini App is the primary project workspace; Bot
  project FSM remains a legacy fallback in PR 5 and must not receive new
  project-management features.
- Design tokens updated to the approved ERA red/violet/magenta system;
  regular cards now use the shared surface/radius/shadow tokens.
- Database foundation added:
  - `ProjectRole` — stable function in a project, not a task;
  - `ProjectMember` — application/participation state plus contribution
    confirmation audit trail;
  - `ProjectMilestone` — ordered project stages;
  - `Task.project_id` — project task link without duplicating `Task`.
- `PortfolioService` now includes confirmed project contribution only when
  the member is accepted/active/completed and `contribution_status` is
  `confirmed`. Pending applications and unverified claims stay out.
- No old Telegram project FSM removal in this block.

Checks:

- `python -m pytest tests/test_project_workspace_foundation.py tests/test_alembic_revision_ids.py tests/test_project_workflow_service.py tests/test_projects_api.py tests/test_domain.py`
  — 40 passed.
- Alembic SQLite smoke:
  `python -m alembic upgrade head` — passed.
- Alembic SQLite smoke:
  `python -m alembic downgrade 0011_pending_chat_join_requests` — passed.
- `npm.cmd run typecheck` — passed.
- `npm.cmd run build` — passed outside sandbox after esbuild hit sandbox
  `Access denied` while loading Vite config.
- `python -m pytest` — 328 passed, 1 existing FastAPI/TestClient warning.
- `git diff --check` — passed.

Known notes:

- `npm.cmd ci` installed frontend dependencies from the committed lockfile;
  `npm audit` reports 2 dependency vulnerabilities (1 moderate, 1 high).
  No `npm audit fix --force` was run because it may introduce breaking
  dependency changes outside this block.
- SQLite downgrade skips dropping `tasks.project_id` because historical
  `0001_initial` uses current `Base.metadata.create_all()`, so a fresh
  SQLite migration already has the new FK before revision `0012`. Production
  Postgres downgrade still drops the FK/index/column from `tasks`.

Next PR 5 block:

- Project Workspace API/service actions: roles, applications, members,
  milestones, task assignment by project, event linking, contribution
  confirmation, and exact Mini App deep links in project notifications.

## Progress vs. the 12-PR plan

- Completed: 4 of 12 full PRs merged (PR 1 + PR 1b deploy follow-up +
  hotfix; PR 2; PR 3; PR 4).
- Current stage: PR 5 — Project Workspace foundation in progress:
  design decision, models and migration first; API/UI workspace actions next.
- Next stage after PR 5: PR 6 — Opportunities + applications +
  recommendations.
