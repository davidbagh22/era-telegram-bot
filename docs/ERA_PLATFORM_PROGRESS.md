# ERA Platform — progress

Single source of truth for the Bot + Mini App platform build-out. Read this
file first in every new session, then `git status` / `git log -1`, then only
the files touched by the current block. Do not re-audit the whole repo.

## Baseline

- Current `main` commit: `2066103f48eceed70837586ebcdc48d73194be7f`
  (PR #126 merge: Admin Opportunity Application Review — the 12th and
  final PR in the original 12-PR plan).
- Prior merges, newest first: `e05d1e2ad` (PR #125, Admin Task
  Submission Review), `3211d21a5` (PR #124, Admin Event
  Moderation), `908896e80` (PR #122, frontend design
  polish pass), `c417f3aa` (PR #121, Leader Mode —
  scope overview + open tasks), `fe4e5f667` (PR #120, Profile +
  Portfolio), `446fd1890` (PR #119, Admin Mode + moderation
  dashboards), `9a0548c` (PR #118, Opportunities),
  `3c3807b` (PR #117, progress-doc-only), `7900a0e` (PR #116, Project
  Workspace UI), `05a04ea` (PR #115, Project Workspace API actions),
  `ba8ff8c` (PR #114, Project Workspace foundation), `5218911` (PR #113,
  Projects read/create/edit), `edc1730` (PR #112, Activity), `4821216`
  (PR #111, design system/Home/Growth), `b3a4e2a` (PR #110 hotfix),
  `905c0ac`/`1a04097` (PR #109/#108, Mini App foundation + deploy),
  `36098e9` (PR #107 merge, pre-platform baseline).
  Full hashes for any of these are in `git log` — not re-listing them all
  here to keep this file from growing without bound.
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

### PR 5 — Project Workspace foundation (merged)

Branch: `pr5-project-workspace-foundation`. PR:
[#114](https://github.com/davidbagh22/era-telegram-bot/pull/114). Merge
commit: `ba8ff8c0052259dc4325548dac2053d8db0b271d`. Both CI checks green
before merge.

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

### PR 5 — Project Workspace API/service actions (merged)

Branch: `pr5-project-workspace-actions`. PR:
[#115](https://github.com/davidbagh22/era-telegram-bot/pull/115). Merge
commit: `05a04eaa7c1f7b95b2e76586bc09f986857d48cd`. Both CI checks green
before merge.

Scope in this block:

- `project_workspace_service` added as the single backend layer for Workspace
  actions and permission checks. It supports project role open/close,
  applications, approve/reject, direct member add, role changes, milestone
  create/complete/status updates, project task create/assign, event linking,
  contribution confirmation and team messaging through the existing safe Bot
  delivery layer.
- Backend permissions are enforced server-side: project author or project
  reviewer/admin can manage; accepted/active/completed members and users
  viewing open projects can read. `projects.review` permission is read via an
  explicit async query, not lazy relationship loading.
- `/api/v1/projects/{project_id}/workspace` endpoints expose overview,
  roles, members/applications, milestones, project tasks, linked events and
  team messages.
- Existing project create/edit/submit/cancel API mutations now explicitly
  commit the session, so Mini App changes persist instead of only being
  reflected in the immediate response object.
- Exact Mini App deep-link helpers were added for project, project
  application, project task and admin moderation routes. Review/application/
  task notifications use URL buttons to the exact object when the Mini App URL
  is configured.
- No old Telegram project FSM removal in this block.

Checks so far:

- `python -m pytest tests/test_project_workspace_service.py tests/test_project_workspace_foundation.py tests/test_projects_api.py tests/test_task_submit_deep_link.py`
  — 36 passed, 1 existing FastAPI/TestClient warning.
- `python -m compileall app/services/project_workspace_service.py app/api/v1/projects.py app/utils/deep_links.py tests/test_project_workspace_service.py tests/test_projects_api.py tests/test_task_submit_deep_link.py`
  — passed.
- `git diff --check` — passed.
- `python -m pytest` — 336 passed, 1 existing FastAPI/TestClient warning.

### PR 5 — Project Workspace UI (merged)

Branch: `pr5-project-workspace-ui`. PR:
[#116](https://github.com/davidbagh22/era-telegram-bot/pull/116). Merge
commit: `7900a0ec3878e888bb6acfe41b044af6e04b626c`. Both CI checks green
before merge.

Scope in this block:

- Mini App `ProjectDetail` now has a Workspace tab next to the existing form.
- Workspace UI reads the real `/api/v1/projects/{project_id}/workspace`
  snapshot and exposes the core leader actions: roles, applications,
  members, contribution confirmation, milestones, project tasks, event
  linking and team messages.
- Project hash deep links like `#/projects/{id}/...` and
  `#/admin/projects/{id}` open the Projects section directly on the target
  project workspace, so Bot notifications do not force the user to search
  again after opening the Mini App.
- No mock project workspace data is used.

Checks so far:

- `npm.cmd run typecheck` — passed.
- `npm.cmd run build` — passed outside sandbox after esbuild hit sandbox
  `Access denied` while loading Vite config.
- `git diff --check` — passed.

### PR 6 — Opportunities + applications + recommendations (merged)

Branch: `era-platform-pr6-opportunities`. PR:
[#118](https://github.com/davidbagh22/era-telegram-bot/pull/118). Merge
commit: `9a0548cc2fdb756c05abad796031aba0d01d996a`. Both CI checks green
before merge.

- **Session-sync note**: this block started from a genuine cross-session
  race — a parallel Claude Code session on this same repo independently
  completed PR 5 as PR #114/#115/#116/#117 while this session was
  mid-draft on the identical scope. Verified against actual `origin/main`
  and `gh pr list` before continuing (not taken on faith), stashed the
  now-superseded local draft, and resumed from the real merged state. No
  code from that stale draft was reused.
- Extracted `app/services/opportunity_service.py` from the existing
  participant bot handler
  (`app/handlers/participant/partner_offers_block16.py`) before adding the
  API — same pattern as PR 3/PR 4/PR 5: `list_active_offers`,
  `remaining_slots`, `apply_to_offer`, `list_my_applications`. Behavior
  preserving, verified against the full suite before new code was added.
  Admin approve/reject (which is where points actually get deducted) stays
  Bot-only for now — that's Admin Mode territory (PR 7), not this block.
- `SavedOpportunity` (`saved_opportunities` table, migration
  `0013_saved_opportunities`) is genuinely new: no bookmark/favorite
  mechanism existed anywhere in the bot before this. Additive, reversible,
  smoke-tested both directions against a fresh SQLite DB
  (`alembic upgrade head` / `alembic downgrade -1`) before being trusted.
- Recommendations (`opportunity_service.recommended_offers`, the "Для
  тебя" tab) use only signals that are actually computable today:
  affordable by current points balance, has open slots, not already
  applied. The brief's suggested reasons ("совпадает направление",
  "подходит возраст", "подходит город") are **not implemented** —
  `PartnerInitiative` has no department/direction/age/city columns
  anywhere in the schema, so claiming that kind of match would be
  fabricated data. Same honesty rule as PR 3's `for_me` event scope and
  PR 4's project targeting.
- New `GET/POST /api/v1/opportunities*`: 4 scopes (`for_me` = real
  recommendations, `all`, `saved`, `mine` = own applications),
  apply/save/unsave. Applying still only ever notifies admins (via the
  same shared `aiogram.Bot` instance pattern from PR 4/PR 5) — it never
  touches points, matching the Bot's existing "баллы спишутся только
  после одобрения" rule exactly.
- Frontend: `OpportunitiesScreen` with the 4 pill tabs, apply/save actions
  wired to the real endpoints, recommendation reasons rendered inline.
  Wired into the bottom nav's "Возможности" tab, replacing the coming-soon
  placeholder from PR 2.
- Tests: `tests/test_opportunity_service.py` (integration, real
  `sqlite+aiosqlite`), `tests/test_opportunities_api.py` (routes,
  dependency overrides). Full suite: 358 passed via `pytest -q`, 273 via
  `python -m unittest discover -s tests` (matches CI), 0 regressions.
  Verified in a real browser against an extended local mock server (not
  committed): all 4 tabs render, apply/save actions POST correctly.

**Known limitation:** no "withdraw a pending application" feature — same
reasoning as PR 3's task-decline gap: no such participant-initiated rule
exists anywhere in the bot today, so nothing was invented for it here.

### PR 7 — Admin Mode + moderation dashboards (merged)

Branch: `era-platform-pr7-admin-mode`. PR:
[#119](https://github.com/davidbagh22/era-telegram-bot/pull/119). Merge
commit: `446fd1890e6908f4d7f5a9e1ca478eb795ad051a`. Both CI checks green
before merge.

- Extracted three pieces of existing bot admin logic into services before
  building the API — same pattern as every prior PR:
  - `app/services/admin_dashboard_service.py`: `dashboard_metrics()` and
    `has_dashboard_access()`, moved out of
    `app/handlers/admin/dashboard_block_a.py`'s private `_metrics()` /
    `_is_admin()`. Preserves the existing rule exactly — **any** active
    permission grant unlocks the dashboard, not just the admin role.
  - `app/services/application_review_service.py` gained
    `request_more_info()` (the "needs info" transition), matching the
    already-existing `approve_application()` / `reject_application()` in
    that same file — `app/handlers/admin/panel.py`'s inline
    `NEEDS_INFO` assignment now calls it, gaining an audit trail it didn't
    have before.
  - `app/services/project_workflow_service.py` gained `decide_project()`
    and `list_projects_for_review()`, moved out of
    `app/handlers/admin/projects_block5_decision.py`'s `decision_finish()`
    — all 5 decisions (`initial_accept`/`venue_approve`/`revise`/
    `postpone`/`reject`), including the `old_status != APPROVED` guard
    that stops points/portfolio credit from being awarded twice on
    re-approval. The Bot handler's permission check was also consolidated
    onto `project_workspace_service.can_review_projects()` (PR 5's
    function) instead of a fourth copy of the same admin-or-permission
    check.
  - All three refactors verified behavior-preserving against the full
    suite before any new code was added.
- New `GET/POST /api/v1/admin/*`: `/dashboard` (same metrics as the Bot
  panel), `/applications` + approve/reject/request-info (registration
  review — approval sends the **identical** notification sequence the Bot
  sends: main menu message, community rules, `sync_user_chat_access()`,
  via the shared `aiogram.Bot` instance), `/projects` + `/decide` (project
  moderation queue, using the exact same 5 actions and notification text
  as the Bot).
- Permission model: `/dashboard` and `/applications/*` require
  `has_dashboard_access()` (admin role, admin ID, or any active
  permission — matches the Bot); `/projects/*` requires
  `can_review_projects()` (admin or the specific `projects.review` grant —
  narrower, matches the Bot's project-review gate exactly).
- Frontend: `AdminScreen` (3 tabs: Дашборд/Заявки/Проекты) now renders by
  default in Admin Mode, replacing the PR 1 placeholder that showed the
  participant `HomeScreen` to admins. The existing `#/admin/projects/{id}`
  deep link still takes priority and opens that exact project, unchanged
  from PR 5.
- Tests: `tests/test_admin_dashboard_service.py`,
  `tests/test_application_review_service.py`,
  `tests/test_project_moderation.py` (integration, real
  `sqlite+aiosqlite`), `tests/test_admin_api.py` (routes, dependency
  overrides). Full suite: 392 passed via `pytest -q`, 307 via
  `python -m unittest discover -s tests` (matches CI), 0 regressions.
  Verified in a real browser against an extended local mock server (not
  committed): all 3 admin tabs render, approve/decide actions POST
  correctly.
- No migrations — no new tables needed. This block was pure service
  extraction + API + UI on top of the existing schema.

**Known limitation:** Admin Mode in this PR covers only the dashboard,
registration applications, and project moderation — not the full Admin
suite from the original brief (Events/Tasks/Opportunities/Partners
content management, Points/Achievements, Communications, Surveys). Those
stay Bot-only for now, per the brief's own phasing (originally PR 9/10,
now folded into later blocks after this narrower "moderation dashboards"
slot).

**Next block:** PR 8 — continuing the Admin/Leader Mode buildout, or
Profile + Portfolio (whichever the next session's brief specifies first —
check for updated instructions before assuming).

### PR 8 — Profile + Portfolio + Growth + resume PDF (merged)

Branch: `era-platform-pr8-profile-portfolio`. PR:
[#120](https://github.com/davidbagh22/era-telegram-bot/pull/120). Merge
commit: `fe4e5f6676c4f80c3e5b9fc4f10f75d6d63969bb`. Both CI checks green
before merge.

- No new service needed — the portfolio aggregation
  (`app/services/portfolio_service.py::build_portfolio_data`) and PDF
  export (`app/services/resume_service.py::build_era_resume`) already
  existed from the Bot's own `/portfolio` flow and are reused verbatim by
  the API; `app/services/growth_service.py::growth_progress_for` (PR 2)
  is reused unmodified for the Growth Level shown on this screen.
- New `GET /api/v1/profile` (identity + Growth Level + the full portfolio:
  projects, events, tasks, volunteer, leadership, badges, certificates,
  recommendations, stats) and `GET /api/v1/profile/resume.pdf` (same PDF
  bytes the Bot sends, returned as `application/pdf` with a
  `Content-Disposition: attachment` header) in `app/api/v1/profile.py`.
  Both require a valid session (`get_current_user`); no separate
  permission check needed since a user's own portfolio is always
  self-viewable, matching the Bot's `/portfolio` command.
- Frontend: `ProfileScreen` replaces the "Профиль" bottom-nav placeholder
  that had been open since PR 2 — this was the last remaining
  `COMING_SOON_TITLES` gap, closing it fully. Shows the Growth Level
  progress bar (reusing the PR 2 `ProgressBar` component), a stats grid
  (`MetricCard` per stat), departments/directions, a "Скачать резюме PDF"
  button (fetches the PDF as a `Blob` with the Authorization header via
  `downloadResumePdf()` in `api/client.ts`, then triggers a client-side
  download — a plain `<a href>` can't carry the bearer token), and one
  section per non-empty portfolio category.
- Tests: `tests/test_profile_api.py` (route shape, PDF content-type/
  `Content-Disposition`, 401 without a token — dependency-override
  pattern matching `tests/test_home_api.py`, including overriding
  `get_settings` so the real `get_current_user` dependency chain
  resolves instead of hitting `Settings()` validation). Full suite:
  395 passed via `pytest -q`, 310 via `python -m unittest discover -s
  tests` (matches CI), 0 regressions. Verified in a real browser
  (mobile viewport) against a temporary local mock server (not
  committed): stats, portfolio sections and the resume download request
  all render/fire correctly; `frontend/.env.local` and the mock server
  were removed after verification.
- No migrations — pure read-only aggregation on top of the existing
  schema.

**Known limitation:** Profile/Portfolio is read-only in the Mini App for
now (no in-app editing of profile fields like city/occupation/skills —
that still goes through the Bot's existing edit flow). Achievements
(`badges`) display whatever the Bot has already awarded; no new
badge-granting logic was added in this block.

**Next block:** PR 9 per the 12-PR plan — next candidate is Leader Mode
or the remaining Admin content-management surfaces (Events/Tasks/
Opportunities/Partners/Communications/Surveys), per the "Final product
decision" and known limitations recorded in PR 7 above — confirm against
any updated brief before starting.

### PR 9 — Leader Mode: scope overview + open tasks (merged)

Branch: `era-platform-pr9-leader-mode`. PR:
[#121](https://github.com/davidbagh22/era-telegram-bot/pull/121). Merge
commit: `c417f3aa78411a4d3249334d2a253fbc8136e90a`. Both CI checks green
before merge.

- New `app/services/leader_service.py`, extracted from
  `app/handlers/leader/panel.py` and `app/handlers/leader/open_tasks.py`
  (previously untested inline query/FSM logic, now covered by
  `tests/test_leader_service.py`): `scope_ids()` (department/direction
  scope, admin bypass — same rule the Bot's `leader:participants`/
  `leader:events`/`leader:projects` callbacks already used),
  `list_scope_participants/events/projects()`, `list_created_tasks()`,
  `create_assigned_task()`, `create_open_task()`,
  `list_open_tasks_with_applications()`, `decide_task_application()`
  (accept/reject with the same capacity guard and Bot notification text
  as before, plus an explicit "only the task's creator may decide"
  check that previously lived only in the handler).
- The Bot handlers were refactored to call these functions instead of
  inline SQLAlchemy queries/FSM logic — verified behavior-preserving via
  the full test suite (416 passed) before anything new was added; no
  user-facing Bot text changed.
- New `GET /api/v1/leader/overview` (scope participants/events/projects
  + the leader's own created tasks + department/direction names),
  `GET/POST /api/v1/leader/open-tasks` (list with nested applications /
  publish a new open task in one call — the Mini App collects all
  fields at once rather than mirroring the Bot's multi-step deadline
  picker FSM), and
  `POST /api/v1/leader/open-tasks/{id}/applications/{user_id}/decide`
  (accept/reject, same rules as the Bot). Gated by
  `user.role in PRIVILEGED_ROLES` (`require_leader`), the same set the
  Bot's `_guard()` checks in both handler files.
- Frontend: `LeaderScreen` (Обзор / Открытые задачи tabs) replaces the
  plain `HomeScreen` fallback that leaders saw with no deep link — the
  last remaining "leader sees the participant Home screen" gap. Overview
  shows scope + participants/events/projects/own-tasks; Open Tasks shows
  existing open tasks with per-applicant accept/reject and a form to
  publish a new one.
- Tests: `tests/test_leader_service.py` (12 cases, real
  `sqlite+aiosqlite` — scope filtering incl. admin bypass, points/
  max_participants validation, capacity guard, non-owner rejection),
  `tests/test_leader_api.py` (9 cases, dependency overrides + mocked
  service calls — permission gate, response shapes, 404/409/403
  mapping). Full suite: 416 passed via `pytest -q`, 331 via
  `python -m unittest discover -s tests` (matches CI), 0 regressions.
  Verified in a real browser (mobile viewport) against a temporary
  local mock server (not committed): overview renders, open-task
  creation and accept/reject both round-trip through the mocked API
  correctly; `frontend/.env.local` and the mock server were removed
  after verification.
- No migrations — pure service extraction + API + UI on top of the
  existing schema.

**Known limitation:** This PR covers scope overview (read-only) and open
(unassigned) tasks only. Assigning a task to one specific member (the
Bot's user-search FSM), AI-assisted event creation, leader proposals
(points/status/office/badge/portfolio nominations), leader reports, and
leader department/direction broadcasts all stay Bot-only for now — they
either need a nontrivial user-search UI or duplicate the AI service
integration, and were judged out of scope for this block. The
`create_assigned_task` service function already exists (extracted from
the Bot's task-assignment flow) but has no Mini App route yet, so
wiring an API endpoint for it later needs no further extraction.

**Next block:** PR 10 per the 12-PR plan — remaining Admin content-
management surfaces (Events/Tasks/Opportunities/Partners/
Communications/Surveys) or the leader actions deferred above, per the
known limitations in PR 7, PR 8 and PR 9 — confirm against any updated
brief before starting.

### Design polish pass (frontend-only, merged)

Branch: `era-platform-design-polish`. PR:
[#122](https://github.com/davidbagh22/era-telegram-bot/pull/122). Merge
commit: `908896e804f7c21eefa384918309fd653e587b8e`. Both CI checks green
before merge. Not a numbered block from the 12-PR plan — a cross-cutting
visual pass across every screen built so far, requested directly
("красивый динамичный дизайн").

- `frontend/index.html` now actually loads Unbounded (headings) and
  Golos Text (body) from Google Fonts — the design system spec named
  these fonts since PR 2, but no `<link>` ever loaded them, so every
  screen was silently rendering in the system-font fallback until now.
- `frontend/src/theme/tokens.css`: a default `button` style (rounded,
  44px touch target, bordered surface, hover/press/disabled/
  focus-visible states, smooth transitions) now applies automatically to
  every plain `<button>` that had no inline style — this covered most of
  the app (Opportunities, Activity, Profile, Leader open tasks, Admin
  applications/projects decisions, Projects create/submit). Buttons that
  already set inline styles (`ProjectWorkspace`, the open-task publish
  button) are untouched, since inline style always wins over the CSS
  element selector — verified no visual regression there. A new
  `.era-btn-primary` class (ERA gradient, white text) was added by hand
  to the one highest-emphasis action per screen (Подать заявку, Хочу
  помочь, Зарегистрироваться, Скачать резюме PDF, Одобрить, Принять,
  Создать черновик, Отправить на рассмотрение) so visual weight matches
  how important each action actually is, rather than every button
  looking the same. `.era-card` adds a hover lift + shadow to every
  `Card`, and a `.era-page` fade-in-up animation now plays when each
  screen mounts.
- `PillTabs` and `BottomNavigation` active states now animate (scale +
  gradient / scale + color) instead of snapping instantly.
- Verified in a real browser (mobile viewport) against a temporary local
  mock server: fonts load (`document.fonts` reports both `loaded`),
  `.era-btn-primary` renders the gradient/white-text CTA look, plain
  buttons render the new bordered look, active pill tabs get the
  gradient + scale, `.era-page` fade-in fires on tab switches — captured
  screenshots of Home and Activity confirming the look. Backend suite
  (416 tests) re-run untouched to confirm this was a frontend-only
  change; `frontend/.env.local` and the mock server removed afterward.
- No backend/API/database changes, no new dependencies (fonts are
  loaded from Google Fonts CDN, not bundled).

### PR 10 — Admin Event Moderation (merged)

Branch: `era-platform-pr10-event-moderation`. PR:
[#124](https://github.com/davidbagh22/era-telegram-bot/pull/124). Merge
commit: `3211d21a5631f393d2a5e75ba7b5fe5a9ab76000`. Both CI checks green
before merge.

- New `can_manage_events()` in `app/services/authorization_service.py`,
  matching the exact `is_full_admin(...) or "events.manage" in
  active_permissions(...)` pattern already used by `can_view_people`/
  `can_manage_people` — replaces a slightly-diverging inline copy of the
  same check that used to live only in
  `app/handlers/admin/events_block6.py` (that copy didn't check
  `is_archived` on the admin-role branch, an inconsistency with every
  other admin gate in the codebase; normalizing it here is a minor
  correctness fix, not a new restriction on any real, non-archived
  admin).
- New `app/services/event_moderation_service.py`: `list_events_for_review()`
  (events with `status == pending_approval`) and `decide_event()`
  (approve/revise/reject — approve sets `APPROVED` + `approved_by` and
  keeps the existing audit-log entry; revise/reject require a non-empty
  comment, matching the Bot's FSM validation, and return the exact same
  notice text the Bot already sent to the event's owner). Extracted from
  `events_block6.py`'s `approve_event` / `event_decision_finish`
  handlers, which now call the service — the 2-step broadcast
  prepare/publish flow, registration/status lifecycle, participant
  management and post-event activities in that same file are untouched
  and still handled inline in the Bot (see known limitation below).
- New `GET /api/v1/admin/events` (review queue) and
  `POST /api/v1/admin/events/{id}/decide` (action: approve/revise/reject
  + comment) in `app/api/v1/admin.py`, gated by a new
  `require_event_reviewer` dependency using `can_manage_events()` — same
  pattern as `require_project_reviewer` from PR 7.
- Frontend: `AdminEventsScreen` adds a fourth "Мероприятия" tab to
  `AdminScreen`, mirroring `AdminProjectsScreen`'s list-with-comment-and-
  decision-buttons layout; "Одобрить" gets the `.era-btn-primary` look
  from the design-polish pass, "На доработку"/"Отклонить" stay neutral.
- Tests: `tests/test_event_moderation_service.py` (6 cases, real
  `sqlite+aiosqlite` — approve/revise/reject transitions, comment
  validation, review-queue filtering), `tests/test_admin_events_api.py`
  (6 cases, dependency overrides + mocked service calls — permission
  gate, 404/422 mapping, notification on approve), plus 2 new
  `can_manage_events` cases in `tests/test_authorization_service.py`.
  Full suite: 430 passed via `pytest -q`, 343 via
  `python -m unittest discover -s tests` (matches CI), 0 regressions.
  Verified in a real browser against a temporary local mock server:
  the Мероприятия tab lists a pending event, "Одобрить" round-trips
  through the mocked API and updates the status shown; `.env.local` and
  the mock server removed afterward.
- No migrations — pure service extraction + API + UI on top of the
  existing schema.

**Known limitation:** Only the initial approve/revise/reject decision is
in the Mini App. The 2-step chat broadcast (prepare/publish), the
post-approval status lifecycle (open/close registration, mark active/
completed), participant & attendance management, and post-event
activities all stay Bot-only — they're Telegram-chat-specific or
substantially larger surfaces better suited to a dedicated future block,
consistent with how PR 7 phased project moderation.

**Next block:** PR 11 per the 12-PR plan — remaining Admin content-
management surfaces (Tasks/Opportunities/Partners/Communications/
Surveys) or the event/leader actions deferred above — confirm against
any updated brief before starting.

### PR 11 — Admin Task Submission Review (merged)

Branch: `era-platform-pr11-task-review`. PR:
[#125](https://github.com/davidbagh22/era-telegram-bot/pull/125). Merge
commit: `e05d1e2ad530d51845c6366dc022a1e5e4731c3c`. Both CI checks green
before merge.

- New `can_manage_tasks()` in `app/services/authorization_service.py`,
  same pattern as PR 10's `can_manage_events()` — replaces an inline
  copy in `app/handlers/admin/task_review_block2.py` that had the same
  `is_archived` inconsistency on the admin-role branch.
- New `app/services/task_review_service.py`: `list_pending_submissions()`
  and `decide_submission()` (approve/revision/reject). Approve is
  idempotent on two axes exactly as the Bot already guaranteed — it
  no-ops with an "already approved" notice if `submission.status` is
  already `approved`, and separately no-ops (still marks approved, no
  second notice) if a point transaction for that user+task already
  exists — and reproduces the private-vs-open-task completion rule (a
  `challenge` task only completes once every accepted `TaskParticipant`
  has an approved submission; a `private` task completes on its own
  approval). Extracted from `approve_submission` /
  `revision_finish` / `reject_finish`, which now call the service.
  `tests/test_system_wide_audit.py`'s
  `test_points_sensitive_flows_have_idempotency_markers` contract was
  retargeted from the handler file to this service file, since that's
  where the `add_points` call and idempotency guarantee actually live
  now — the invariant it guards is unchanged, only its address moved.
- New `GET /api/v1/admin/task-submissions` and
  `POST /api/v1/admin/task-submissions/{id}/decide` in
  `app/api/v1/admin.py`, gated by `require_task_reviewer`
  (`can_manage_tasks()`) — same shape as PR 10's event-review routes.
- Frontend: `AdminTasksScreen` adds a fifth "Задания" tab to
  `AdminScreen`, mirroring `AdminEventsScreen`'s
  list-with-comment-and-decision-buttons layout; "Одобрить и начислить
  баллы" gets `.era-btn-primary`.
- Tests: `tests/test_task_review_service.py` (8 cases, real
  `sqlite+aiosqlite` — private-task completion + point award,
  approve-idempotency, open-task completion only when every member is
  approved, revision/reject comment validation, review-queue
  filtering), `tests/test_admin_task_submissions_api.py` (6 cases,
  dependency overrides + mocked service calls), plus 1 new
  `can_manage_tasks` case in `tests/test_authorization_service.py`.
  Full suite: 445 passed via `pytest -q`, 357 via
  `python -m unittest discover -s tests` (matches CI), 0 regressions.
  Verified in a real browser against a temporary local mock server: the
  Задания tab lists a pending submission, "Одобрить и начислить баллы"
  round-trips through the mocked API; `.env.local` and the mock server
  removed afterward.
- No migrations — pure service extraction + API + UI on top of the
  existing schema.

**Known limitation:** Only task-submission review (approve/revision/
reject) is in the Mini App. Creating tasks/open challenges from Admin
Mode (as opposed to the Leader Mode open-task creation from PR 9),
partner/opportunity content management, communications/broadcasts, and
surveys all stay Bot-only for now — each is its own coherent surface
better suited to a dedicated future block.

**Next block:** PR 12 per the 12-PR plan — remaining Admin content-
management surfaces (Opportunities/Partners/Communications/Surveys) or
the event/leader/task actions deferred above — confirm against any
updated brief before starting.

### PR 12 — Admin Opportunity Application Review (merged)

Branch: `era-platform-pr12-opportunity-review`. PR:
[#126](https://github.com/davidbagh22/era-telegram-bot/pull/126). Merge
commit: `f01e570d49b4f7390de7a4bda0cffbb117554d2d`. Both CI checks green
before merge. This closes the 12-PR plan.

- New `can_manage_partners()` in `app/services/authorization_service.py`,
  same pattern as PR 10/PR 11's `can_manage_events()`/`can_manage_tasks()`.
  `app/handlers/admin/partners_admin.py::admin_ok()` (shared by both
  partner-management handler files) now delegates to it instead of a
  local inline copy — this one already checked `is_archived` correctly,
  so this is a pure DRY consolidation, not a bugfix like PR 10/11's.
- Extended the existing `app/services/opportunity_service.py` (from
  PR 6) rather than creating a new file, since offer-application review
  is squarely part of the Opportunities domain it already owns:
  `list_pending_offer_applications()` and `decide_offer_application()`
  (approve/reject). Approve reproduces the Bot's exact two-step guard —
  a non-pending application short-circuits with an "already processed"
  notice, and an approve with an insufficient point balance leaves the
  application `pending` (so an admin can retry once the participant
  earns more points) rather than silently failing. Extracted from
  `application_approve`/`application_reject` in
  `app/handlers/admin/partner_offers_block16.py`, which now call the
  service. Two source-text contract tests
  (`tests/test_partner_offers_block16.py::test_admin_flow_contract` and
  `tests/test_system_wide_audit.py::test_points_sensitive_flows_have_idempotency_markers`)
  were retargeted from the handler file to `opportunity_service.py`,
  since that's where the `add_points` idempotency guarantee they check
  for actually lives now — same pattern as the PR 11 retarget, the
  invariant itself is unchanged.
- New `GET /api/v1/admin/offer-applications` and
  `POST /api/v1/admin/offer-applications/{id}/decide` in
  `app/api/v1/admin.py`, gated by `require_offer_reviewer`
  (`can_manage_partners()`).
- Frontend: `AdminOffersScreen` adds a sixth "Возможности" tab to
  `AdminScreen` — list of pending applications with participant name,
  offer cost and current balance, plus approve/reject buttons
  (`.era-btn-primary` on approve).
- Tests: 9 new cases added to `tests/test_opportunity_service.py`
  (approve deducts points exactly once and is idempotent on retry,
  insufficient-balance leaves the application pending, reject, unknown
  action raises, review-queue filtering) — bringing that file to 18
  cases total; `tests/test_admin_offer_applications_api.py` (5 cases,
  dependency overrides + mocked service calls); plus 1 new
  `can_manage_partners` case in `tests/test_authorization_service.py`.
  Full suite: 456 passed via `pytest -q`, matching count via
  `python -m unittest discover -s tests` (CI parity confirmed), 0
  regressions. Verified in a real browser against a temporary local
  mock server: the Возможности tab lists a pending application and
  "Одобрить и списать баллы" round-trips through the mocked API and
  updates the shown status; `.env.local` and the mock server removed
  afterward.
- No migrations — pure service extension + API + UI on top of the
  existing schema.

**Known limitation:** Only offer-application review (approve/reject) is
in the Mini App. Creating/editing partners and partner offers (currently
a pipe-delimited text form in the Bot), communications/broadcasts, and
surveys all remain Bot-only — each is a distinct, non-trivial UI surface
that was judged out of scope for closing out the 12-PR plan. These, plus
every other "Known limitation" recorded in PR 7 through PR 11 above,
are the natural backlog for whichever numbered or unnumbered block comes
next.

### PR 13 — Production Readiness Audit + Critical Hardening (merged)

Branch: `era-platform-pr13-production-readiness`. PR:
https://github.com/davidbagh22/era-telegram-bot/pull/127. Merge commit:
`2066103f48eceed70837586ebcdc48d73194be7f`.
Not part of the 12-PR plan — a full audit + hardening block requested
after the plan closed, scoped down honestly from a much larger brief
(7 PRs, E2E suites, external monitoring, legal review) to what a single
session can genuinely implement and verify, with the rest documented as
backlog rather than faked.

- New `docs/PRODUCTION_READINESS_AUDIT.md` — full findings table with
  severity/status per item, not a theoretical list; every "Fixed" item
  has a real diff and test in this PR.
- **Real bug found and fixed**: `app/handlers/admin/rights_block6.py`
  used `PERMISSION_LABELS` without importing it — a `NameError` on every
  admin open of a user's permissions screen. Found by adding a
  correctness-only `ruff` pass (`E9,F` rules) to CI, which is exactly
  why that check was worth adding. Fixed with a regression test
  (`tests/test_rights_block6_permissions_keyboard.py`).
- Security fixes: `hmac.compare_digest` for the Telegram webhook secret
  (was a plain `!=`); a startup guard (`Settings.assert_safe_for_deployment`)
  that refuses to start if `DEV_AUTH_ENABLED=true` on a Render deployment
  (would otherwise let anyone bypass `initData` verification); a new
  `/ready` endpoint that actually checks database connectivity (`/health`
  stays a dependency-free liveness check); `init_data_max_age_seconds`
  default reduced from 24h to 1h; a Redis-backed rate limiter
  (`app/api/rate_limit.py`, fails open) on `/api/v1/miniapp/auth`; basic
  security response headers (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, HSTS on HTTPS).
- Audit logging added for chat-access actions that weren't previously
  recorded: `sync_user_chat_access` now writes one summary `AuditLog` row
  per sync (`chat_access.synced`, including a `failed` count so admins
  can see when a Telegram API hiccup left permissions out of sync), and
  `handle_chat_join_request` logs `chat_access.join_request_approved`/
  `_declined`. The existing, already-mature chat-moderation system
  (join-request handling, auto-restrict on join, real-time per-message
  moderation gate, `sync_user_chat_access` wired into every
  approve/block/unblock flow) needed this one gap closed, not a rebuild
  — see the audit doc for the full assessment of what was already solid.
- CI (`.github/workflows/ci.yml`) now also: builds and type-checks the
  frontend (`npm run build`) in a new `frontend` job — previously CI
  never touched `frontend/` at all; runs `ruff check app --select E9,F`
  (blocking); runs `pip-audit --strict` (blocking — currently clean, 0
  known vulnerabilities); runs `npm audit --audit-level=high`
  (non-blocking for now — found one real moderate/high dev-only
  `esbuild`/vite advisory that needs a breaking Vite major-version
  upgrade, tracked as backlog rather than force-failing this PR over an
  unrelated pre-existing issue).
- New `docs/AUTHORIZATION_MATRIX.md` (Mini App/API-layer object-level
  authorization per endpoint, cross-referencing the existing
  `docs/ROLE_PERMISSION_MATRIX.md` for the bot's grant model),
  `docs/DEPLOYMENT_RUNBOOK.md` (env vars, migrations, smoke test,
  rollback, troubleshooting table — grounded in the real `render.yaml`/
  `Dockerfile`), `docs/DATA_INVENTORY.md` (real field-by-field inventory
  of `users` and related tables, explicit unresolved gaps: no
  `consent_log` table, no minors/age-gating logic despite `birth_date`
  being collected — flagged as the platform owner's decision, not
  something a technical PR can resolve unilaterally).
- `docs/BACKUP_AND_RECOVERY.md` already existed (from a parallel session)
  and is already real and thorough — daily automated backup +
  isolated-Postgres restore verification in CI, not just documented as a
  plan. Left as-is, referenced from the new docs above.
- Tests: 15 new cases across `tests/test_config_deployment_safety.py`,
  `tests/test_rate_limit.py`, `tests/test_chat_access_audit.py`,
  `tests/test_rights_block6_permissions_keyboard.py`. Full suite: 471
  passed via `pytest -q`, 0 regressions. `ruff check app --select E9,F`
  clean. Frontend build clean. Alembic: unchanged, one head
  (`0013_saved_opportunities`) — no migrations in this PR.

**Known limitation / explicit backlog** (see the audit doc for full
detail, not repeated here): no E2E test suite, no external error
monitoring (Sentry-class tooling), no real production domain/TLS setup
from this environment (needs the owner's Render access), rate limiting
not yet extended to every admin/leader decide-endpoint, Vite major-version
upgrade for the `esbuild` advisory, and the two explicitly-flagged
organizational/legal items (consent-log schema needs real policy text
from the owner; minors/age-gating needs an owner + legal decision before
any technical fix is meaningful).

**Next block:** owner directed a continuous run through the remaining
backlog (design system → functional stabilization → E2E → rate limiting →
file security → consent/minors technical scaffolding → dependency
upgrade → live chat/broadcast re-verification → production
acceptance), reported per-PR below rather than re-planned from scratch.

### PR 14 — Unified Design System + Mobile/Telegram Theming (merged)

Branch: `era-platform-pr14-design-system`. Frontend-only — no backend/API
change, no migration.

- **Real gap found and fixed**: `getColorScheme()` (`telegram/webApp.ts`)
  existed since PR2 but was never called anywhere — the Mini App ignored
  Telegram's dark theme entirely and always rendered light, even inside a
  dark-themed Telegram client. Added `applyTelegramTheme()`, called once
  synchronously in `main.tsx` (avoids a flash of the wrong theme) and
  again from `initTelegramWebApp()` (`useAuth.ts`), which also subscribes
  to Telegram's `themeChanged` event so switching theme mid-session
  updates live. `tokens.css` gained a `:root[data-theme="dark"]` block
  overriding surface/text/border/shadow/status tokens; brand colors
  (red/violet/magenta/gradient) are unchanged in dark mode — verified in
  a local browser session (`document.documentElement.dataset.theme`
  toggle) that computed `background-color`/`color`/`--era-error` all
  flip correctly.
- Fixed two inline style fallbacks (`OpenTasksTab.tsx`, `ProfileScreen.tsx`)
  that hardcoded `var(--era-error, #E5342B)` where the fallback hex
  didn't match the real token (`#d92d20`) — the fallback was dead code
  with a wrong value, since `tokens.css` is always loaded globally;
  simplified to `var(--era-error)`.
- Added `env(safe-area-inset-top, 0px)` top padding to `UserLayout`,
  `AdminLayout`, `LeaderLayout`, and `StatusBanner` (used standalone by
  Pending/Blocked/AuthError screens). `index.html` sets
  `viewport-fit=cover`, so content can render under a device notch/status
  bar without this — bottom nav already handled the equivalent bottom
  inset, top was missing for every layout.
- Audited all 17 screens/tabs using the `useAsync` loading pattern:
  confirmed every one renders distinct loading/error/empty-ready states
  (no screen silently shows nothing or leaves an unhandled rejection) —
  this closes the "per-screen loading/error/empty audit" item PR13 had
  left as an explicit, unchecked backlog item.
- New `docs/UI_DESIGN_SYSTEM.md` — the token table, component-usage
  table, the loading/error/empty pattern contract, and the documented
  exceptions (literal `#fff` on brand-color backgrounds; the safe-area
  additions above).
- Verification: `npm run build` (tsc + vite) clean; manual browser check
  at a 375×812 mobile viewport confirmed light theme renders correctly
  and toggling `data-theme` to `"dark"` correctly flips computed
  `background-color`/`color`/CSS custom properties; full backend
  `pytest -q` re-run as a regression check (frontend-only change, but no
  surprises) — see PR for the exact count.

**Known limitation / explicit backlog**: no Storybook/visual-regression
tooling — screen consistency is enforced by `docs/UI_DESIGN_SYSTEM.md` +
code review, not automated; loading state stays a plain "Загрузка…" text
(no spinner/skeleton) — consistent everywhere already, a skeleton
upgrade is a separate cosmetic decision, not a production-readiness gap.

### PR 15 — Functional/UX Stabilization: Silent Action Failures (merged)

Branch: `era-platform-pr15-functional-stabilization`. Frontend-only — no
backend/API change, no migration. Distinct from PR14: that closed the
*fetch-time* loading/error/empty gap; this closes a separate,
*mutation-time* gap the audit hadn't looked at yet.

- **Real bug found and fixed, repeated across 9 screens**: every mutating
  action (approve/reject/request-info, event/project/task/offer
  moderation decisions, event registration/cancellation, task claim,
  opportunity apply/save, project creation, leader open-task
  create/decide) called its API function inside `try { ... } finally`
  with **no `catch`**. On failure — a network error, a permission edge
  case, or exactly the "two admins decide the same item at once"
  concurrency scenario the ТЗ calls out explicitly — the promise
  rejection propagated unhandled: the button silently stopped being
  "busy" and the screen gave zero indication anything had gone wrong.
  From the user's perspective this is functionally a dead button.
  Affected: `AdminApplicationsScreen`, `AdminEventsScreen`,
  `AdminOffersScreen`, `AdminProjectsScreen`, `AdminTasksScreen`,
  `OpportunitiesScreen`, `ProjectsList`, `activity/EventsTab`,
  `activity/TasksTab`, `leader/OpenTasksTab`.
- Added `describeActionError()` (`api/client.ts`) — backend error
  `detail` values are machine codes (`already_approved`, `no_slots`,
  `insufficient_points`, `cannot_change_plans`, etc., enumerated from
  every `HTTPException` in `app/api/v1/*.py` touched by these screens),
  not sentences. This translates the known ones to Russian and falls
  back to a readable generic message with the raw code attached for
  anything unmapped, instead of either a raw code or silence.
- Each affected screen now has an `actionError` (or per-form) state:
  cleared before the call, set from `describeActionError()` on failure,
  rendered as a small error line near the action. `leader/OpenTasksTab`
  additionally had a *wrong*-message bug fixed: its create-task form
  reused the client-side validation message ("Заполните название,
  описание и дедлайн") for server-side failures too — so a real backend
  error after valid input would misleadingly tell the leader their form
  was incomplete. Split into separate `formError`/`actionError` states.
- Verification: `npm run build` clean; re-grepped the whole
  `frontend/src` tree for any remaining `async` function without a
  `catch` — none found; spot-checked `ProjectDetail.tsx`/
  `ProjectWorkspace.tsx` (not flagged by the original grep) to confirm
  they already had correct error handling via their own `run()`
  wrapper/`.catch()` — no regression risk there; full backend
  `pytest -q` re-run (frontend-only change) — see PR for the exact count.

**Known limitation / explicit backlog**: the error-code dictionary
covers the codes these 10 specific screens can actually receive, not
every code in the codebase (e.g. `ProjectWorkspace`'s ~25 `WorkspaceError`
codes are untouched — that screen already had its own generic-but-honest
error handling, just not code-specific messages); extending coverage
there is a natural follow-up, not a blocker. Bot-side (aiogram handler)
error handling was also spot-checked in this block and found already
correct (`cabinet.py`'s PDF-generation failure path logs and notifies the
user; no bot-side silent-failure pattern found).

### PR 16 — E2E Test Suite (Participant/Leader/Admin) (merged)

Branch: `era-platform-pr16-e2e-tests`. Closes the audit's #13 backlog item
("no E2E test infrastructure"). Real end-to-end: a real FastAPI backend, a
real (throwaway, file-based) SQLite database, and the actual production
frontend build served exactly as `app/webapp.py` serves it in production
(`/app/`) — no mocked API layer.

- **Critical bug #1 found by this suite itself, not by manual review**
  (audit finding #18): `index.html` referenced its JS/CSS bundle at an
  absolute root path (`/assets/index-....js`), but
  `app/webapp.py::_mount_frontend` only mounts static files at `/app`,
  never at the domain root. A real browser resolves an absolute path
  against the origin root regardless of what page it's on, so that
  request always 404'd — **the Mini App most likely never rendered any
  UI for a real user**, just an empty `<div id="root">`. Confirmed
  directly against the live production domain both ways:
  `GET .../assets/index-g9wS8NyS.js` → 404,
  `GET .../app/assets/index-g9wS8NyS.js` → 200. Fixed with one line —
  `base: "/app/"` in `frontend/vite.config.ts` — which makes Vite rewrite
  both the bundle paths and the `<link rel="icon">` favicon path
  correctly; rebuilt and confirmed the new `dist/index.html` references
  `/app/assets/...` throughout. This was invisible to every prior
  verification step in PR13/14/15 because those only checked that
  `/app/` returned HTML with the right commit/asset hash — never that the
  referenced asset URL itself actually loaded.
- **Critical bug #2, the most serious finding of the entire audit series,
  also found by this suite and not by manual review** (audit finding
  #19): after fixing bug #1, the admin/leader E2E specs still failed —
  an admin's "approve" call returned `200 OK`, but re-fetching the
  pending queue in the same test still showed the applicant as pending.
  Root cause: `app/api/deps.py::get_session()` opened a session and
  yielded it, but **never called `session.commit()`**. SQLAlchemy rolls
  back anything uncommitted when a session closes — so **every mutating
  Mini App endpoint except `app/api/v1/projects.py`** (which already had
  its own independent workaround, `_commit_if_possible`, apparently added
  earlier for exactly this reason but never generalized) **computed the
  correct result and returned 200, but never actually wrote it to the
  database**: admin approve/reject/decide across applications, events,
  tasks, and offers; event registration/cancellation; task claiming;
  leader open-task creation and decisions. All of it looked successful in
  the UI and reverted the instant the request ended. The existing 471
  unit/API tests never caught this because their `get_session` override
  reuses one long-lived session object for the whole test — a session
  sees its own uncommitted changes without needing a commit, which
  perfectly masked the missing commit in the real dependency. Fixed by
  adding `await session.commit()` after `yield` (and `rollback()` on
  exception) directly in `get_session()` — one fix for every route,
  instead of requiring every handler to remember a manual commit. Full
  `pytest -q` re-run afterward confirmed zero regressions.
- **Login without a real Telegram session**: `useAuth.ts` now reads an
  optional `?devTelegramId=<id>` query param and forwards it to
  `POST /api/v1/miniapp/auth`. The backend only honors that field when
  `DEV_AUTH_ENABLED=true`, which `Settings.assert_safe_for_deployment()`
  (PR13) refuses to allow on a Render deployment — so this is inert
  against the real deployed bot regardless of what's in a URL, verified
  by reading `app/api/v1/auth.py`'s exact gating logic before adding it.
- `scripts/e2e_seed.py` — seeds a throwaway SQLite DB via
  `Base.metadata.create_all` (the same approach the existing unit test
  suite already uses against SQLite, not the real Alembic chain — several
  accumulated migrations aren't wrapped in `batch_alter_table()` and
  SQLite's limited `ALTER TABLE` support would break them; migration
  correctness is verified separately against real Postgres) with four
  fixed-ID users (participant/leader/admin/a pending applicant) and one
  future open-registration event.
- `frontend/e2e/{participant,leader,admin}.spec.ts` (Playwright) — one
  scenario per role, each exercising a real state change through the
  full stack, not just a page render: participant registers for the
  seeded event; leader creates a real open task through the form; admin
  approves the seeded pending applicant and sees them leave the queue.
  See `frontend/e2e/README.md` for the full scope note and how to run
  locally.
- New CI job `e2e` (`.github/workflows/ci.yml`): spins up a `redis:7`
  service container (the app's FSM storage needs a reachable Redis even
  for this), seeds the DB, builds and serves the real frontend, starts
  the real backend, waits on `/health`, runs the three specs, uploads
  the Playwright report as an artifact on failure.
- Verification: `npm run build` clean with the new devDependency;
  `ruff`/`compileall` clean on the new `scripts/e2e_seed.py`; ran the
  seed script locally against a throwaway SQLite file end-to-end
  (confirmed the four users and event are created correctly) — the full
  server+Playwright run itself needs a local Redis this environment
  doesn't have, so it's verified by CI rather than locally; full backend
  `pytest -q` re-run as a regression check.

**Known limitation / explicit backlog**: three scenarios, one per role —
not full coverage of every screen/action (that's what PR15's manual
audit + the existing 471 unit/integration tests are for). Concurrent-
decision races, file/portfolio upload, and the chat/registration
addendum's own scenario list are explicitly out of scope here, covered
by other, dedicated blocks instead of being folded into this one.

### PR 17 — Rate Limiting on Remaining Admin/Leader Endpoints (merged)

Branch: `era-platform-pr17-rate-limiting`. Closes audit finding #11
("decide-endpoints in Admin/Leader Mode still without limits" — PR13 had
only covered `/api/v1/miniapp/auth`).

- New `enforce_admin_action_rate_limit` (`app/api/v1/admin.py`) applied
  to all 7 mutating endpoints: application approve/reject/request-info,
  and project/event/task-submission/offer-application decide. New
  `enforce_leader_action_rate_limit` (`app/api/v1/leader.py`) applied to
  all 3: assigned-task create, open-task create, open-task application
  decide. Both reuse the existing `app/api/rate_limit.py` helper (Redis
  fixed-window, fails open) from PR13 — same shared-budget-per-router
  design as the auth endpoint's limiter, so rotating between an admin's
  different decide endpoints doesn't reset the budget. 30 requests/60s —
  generous enough that no real admin working through a queue by hand
  would ever hit it, tight enough to blunt a stolen-token spam scenario.
- Tests (`tests/test_admin_leader_rate_limiting.py`): under/over-limit
  behavior for both dependencies, plus a dependency-wiring check that
  actually inspects each router's registered `POST` routes and asserts
  the rate-limit dependency is present on all 7 (admin) / 3 (leader) of
  them — not just that the function works in isolation, which would have
  silently passed even if a route forgot to declare it.
- Verification: `ruff`/`compileall` clean; full `pytest -q` re-run — see
  PR for the exact count, zero regressions expected (additive dependency
  only, no endpoint behavior changed for requests under the limit).

**Known limitation / explicit backlog**: participant-facing mutations
(event registration/cancellation, task claim, opportunity apply/save,
project creation) remain unlimited — audit finding #11 scoped this to
Admin/Leader Mode specifically, since a compromised participant token
has far less blast radius than a compromised admin/leader one; extending
coverage there is a natural, low-risk follow-up if ever prioritized.

### PR 17b — File/Portfolio Upload Security Review (docs only, no code change)

A deliberate deep-dive re-check of audit finding #10, not a rubber-stamp:
searched the entire `app/` tree for any place that downloads Telegram
file content to local disk (`bot.download_file`/`download_file`) —
found none. Confirmed the text fields around portfolio uploads
(`portfolio_upload_title`/`_description` in
`app/handlers/participant/growth.py`) already use `clean_text()` with
length caps (255/1500 chars). Traced `PortfolioItem.url` — present in
the model and exposed in the Mini App API's `PortfolioEntryOut` — through
every one of its ~10 creation call sites and confirmed none of them ever
sets it, and `frontend/src/screens/ProfileScreen.tsx` never renders it;
it's a genuinely dead field, not an XSS vector waiting to happen.

**Result: no issue found.** Recorded as audit finding #20 with the exact
grep/trace evidence rather than skipped or asserted without checking.
No code change — the dead `url` field was deliberately left alone rather
than removed, since dropping a DB column needs a migration for a purely
cosmetic cleanup, which is unnecessary architectural churn for zero
security benefit.

### PR 18 — Consent Log Technical Foundation + Minors Scaffolding (merged)

Branch: `era-platform-pr18-consent-minors-scaffolding`. Closes audit
findings #16/#17 as "technical foundation ready", explicitly **not** as
"legally compliant" — that distinction is the whole point of this PR.

- New `ConsentLog` model (`app/database/models.py`) + additive migration
  `0014_consent_log` (upgrade/downgrade smoke-tested against a temp
  SQLite DB before merging, per the project's migration-PR convention).
  Does not touch `users.personal_data_consent`, which remains the bool
  actually checked anywhere in the app.
- `app/services/consent_service.py`: `record_consent()`/`latest_consent()`.
  `CURRENT_POLICY_VERSION` is a plain placeholder string
  (`"unset-v1"`) — the module's docstring is explicit that nothing here
  writes, validates, or defines policy *content*; it only makes sure
  that once real policy text exists, one constant change is enough to
  start versioning consent against it, with every prior record still
  showing what it was actually given under. Wired into
  `app/repositories/users.py::create_user_from_registration` — one
  additive `record_consent()` call after the existing user creation,
  no change to registration behavior or text the user sees.
- `app/services/minors_service.py::is_minor(age)` — a pure function
  returning `True`/`False`/`None` (unknown when age wasn't collected).
  Not used for any access control, gating, or restriction anywhere.
  Its one call site is a new, admin-only informational line
  ("Несовершеннолетний (по анкете)") in
  `app/services/admin_user_card.py` — visible to admins reviewing a
  user's card, changes nothing about what anyone can do. Explicitly the
  boundary the ТЗ drew: prepare the technical capability, leave the
  legal/organizational decision to the owner.
- Tests (`tests/test_consent_and_minors.py`, 10 cases): `is_minor()`
  edge cases (unknown/minor/adult/custom threshold); `record_consent`/
  `latest_consent` against a real SQLite session; a dedicated
  integration test proving the registration wiring actually writes a
  `ConsentLog` row (not just that `record_consent()` works in
  isolation); three admin-card tests confirming the new label renders
  correctly for minor/adult/unknown-age cases.
- Verification: `ruff`/`compileall` clean; `alembic heads` — single
  head; upgrade/downgrade smoke test passed; full `pytest -q` re-run —
  see PR for the exact count.

**Explicit, deliberate non-scope** (see `docs/DATA_INVENTORY.md` §5–6):
no real policy text, no consent UI/flow changes, no age-gating at
registration, no legal-guardian consent flow, no restriction of any
kind based on `is_minor()`. All of the above require the platform
owner's decision (and likely counsel) first — a technical PR cannot and
should not make that call unilaterally, and this one doesn't pretend to.

### PR 18b — Vite/esbuild Dependency Upgrade (merged)

Branch: `era-platform-pr18b-vite-upgrade`. Closes audit finding #7c
(PR13's non-blocking `esbuild`/Vite dev-server-only advisory).

- Vite `^5.4.11` → `^8.2.1`, `@vitejs/plugin-react` `^4.3.4` → `^6.0.5`
  (the version Vite 8 actually requires as a peer dependency).
  `npm audit` — clean, 0 vulnerabilities (was 1 moderate + 1 high).
- Verification: `npm run build` clean (57 modules, same output shape);
  `npm run typecheck` clean; started the Vite 8 dev server and checked it
  in the browser — same expected `AuthErrorScreen` render outside a real
  Telegram session as before the upgrade, no new console/server errors;
  `vite.config.ts` needed no changes (`base: "/app/"` and `server.host`
  are stable across this range).
- CI: `npm audit --audit-level=high` in `.github/workflows/ci.yml` is
  blocking again — the non-blocking `|| echo "::warning..."` fallback
  from PR13 existed specifically to avoid failing CI over this exact
  advisory before a fix was available; now that it's fixed, leaving it
  non-blocking would just mask the *next* real advisory.

**Known limitation**: this PR's own CI run is the regression check for
the frontend — no backend files changed, so the full backend `pytest`
suite wasn't re-run locally for this one (CI's `test` job still runs it
before merge, per the existing gate).

### PR 18c — Chat/Registration/Broadcast 12-Point Re-Verification (docs only)

Re-checks the addendum's 12-point checklist against the current code
(after PR14–18b's changes), the way it's actually possible to verify in
this environment — see "explicit capability gap" below for what isn't.

1. **Незарегистрированный/неполная регистрация/pending не может писать** —
   `check_chat_access()` (`app/services/chat_access_service.py`): `user is
   None` → `not_registered`; `application_status != APPROVED` →
   `not_approved`, both `pending=True`. Confirmed unchanged since PR13.
2. **Одобрение открывает права автоматически** — every approval call site
   (`app/api/v1/admin.py`, `app/handlers/admin/panel.py`) calls
   `sync_user_chat_access()` immediately after `approve_application()`.
3. **Отклонение сохраняет ограничение** — `application_status ==
   REJECTED` returns `allowed=False` explicitly, not merely "not yet
   approved".
4. **Повторный вход не обходит проверку** — `check_chat_access()` always
   re-derives from current DB state keyed by `telegram_id`, never cached;
   a rejoin/relogin re-evaluates from scratch every time.
5. **Ручная блокировка имеет приоритет** — confirmed by reading
   `app/handlers/admin/rights_block6.py::block_toggle`: sets
   `is_blocked` then calls `sync_user_chat_access()` immediately, and
   `check_chat_access()` checks `is_blocked` *before* `application_status`
   — an approved-and-blocked user is restricted, not treated as approved.
6. **Приветствия не дублируются** — `welcome_members()` fires once per
   Telegram `new_chat_members` update (Telegram's own event, not
   re-triggerable by this code); the private-chat approval welcome has an
   explicit `already_approved` short-circuit in `panel.py` that skips
   re-sending it.
7. **Личные уведомления не попадают в общий чат / общая рассылка
   действительно уходит в общий чат / комбинированная не дублирует** —
   `broadcast_detailed()`'s `_dedupe_recipients()` (`notification_service.py`)
   dedupes the recipient list before sending; delivery is explicitly
   per-`chat_id` (a personal notification's `chat_id` is the user's
   Telegram ID, a group broadcast's is the configured chat ID — the
   function has no code path that mixes the two without the caller
   explicitly listing both).
8. **Бот имеет административные права в чате** — **could not check**, see
   below.

Verification run: `tests/test_admin_notification_recipients.py`,
`test_broadcast_service.py`, `test_chat_access_service.py`,
`test_chat_access_audit.py`, `test_fsm_global_recovery.py`,
`test_scheduler_notification_delivery.py` — 34 passed + 7 subtests,
targeted re-run.

**Explicit capability gap, not a finding of "works"**: verifying items
1–7 *live* — a real unregistered account trying to post, a real pending
applicant, a real block taking effect in a live chat — needs multiple
real Telegram test accounts this environment doesn't have. Item 8 (bot's
actual admin rights in the real chat) needs either the bot's own
`BOT_TOKEN` (not available here) or a connected browser with the owner's
real Telegram session (`list_connected_browsers` returned empty — no
browser connected in this session). Sending a real broadcast to the real
general chat to prove item 7's delivery would affect real chat members
and wasn't done without the owner's explicit per-action confirmation
(see the safety boundary stated at the start of this platform-hardening
sequence). **What's reported above is code-level re-verification against
the actual shipped implementation, backed by passing automated tests —
not a substitute for the owner clicking through the real bot once.**

No code change — this block found no regression to fix.

### PR 19 — Final Production Acceptance (merged)

Branch: `era-platform-pr19-production-acceptance`. The closing PR of the
PR13–PR19 hardening block.

- New `docs/FINAL_PRODUCTION_ACCEPTANCE.md` — the single document that
  states plainly what "production ready" does and doesn't cover, per the
  block's own rule that phrase is only used when no unresolved Critical
  or High finding remains. Corrected two stale statuses in
  `docs/PRODUCTION_READINESS_AUDIT.md` while confirming this: finding #3
  (rate limiting) updated to **Fixed** (PR17 closed the "остальные —
  Backlog" part), finding #13 (E2E infra) updated to **Fixed** (PR16
  built it, and it immediately found both Critical findings #18/#19 —
  not hypothetical value, realized value).
- Final regression, run immediately before opening this PR: `alembic
  heads` (single head), `ruff check app --select E9,F` (clean),
  `compileall` (clean), `pip-audit --strict` (clean), `npm audit
  --audit-level=high` (clean), `npm run build` (clean), full `pytest -q`
  — **489 passed, 7 subtests passed, 0 failures**.
- Explicit, named owner action items (not faked as done): production
  domain/TLS from this environment, external error monitoring, real
  consent-policy text, the minors/age-gating legal decision, and
  confirming the bot's admin rights in the real Telegram chat(s) —
  each stated once, precisely, in the new document rather than implied
  away or silently dropped.

**This closes the PR13–19 block.** Everything in it is merged to `main`,
deployed to the real Render service, and verified against the live
`/health`/`/ready` endpoints and (where the built frontend changed) the
actual served asset URLs — not just "code exists."

### PR 20 — Chat Menu Button → Direct Mini App Launch + Privacy Policy Draft (merged)

Branch: `era-platform-pr20-menu-button-privacy-draft`. Direct follow-up
request after the PR13–19 block closed.

- **Real, user-visible fix**: Telegram's "chat menu button" (the button
  next to the message input — distinct from the "🔥 Открыть ЭРА"
  reply-keyboard button in `main_menu()`, which only appears after
  `main_menu()` has been sent at least once) was set to
  `MenuButtonDefault()` (plain commands list) on every startup. New
  `app/webapp.py::_chat_menu_button()` switches it to
  `MenuButtonWebApp` — opens the Mini App in one tap — whenever
  `Settings.effective_miniapp_url` is actually configured (confirmed
  live: `MINIAPP_AUTH_SECRET` is set on production — a real, non-garbage
  `initData` parsing error came back from `/api/v1/miniapp/auth`, not
  the `miniapp_auth_not_configured` 500 that would mean otherwise).
  Falls back to the commands list if it isn't configured, matching the
  existing safety pattern for the reply-keyboard button. Tests:
  `tests/test_chat_menu_button.py`.
- New `docs/PRIVACY_POLICY_DRAFT.md` — a draft personal-data-processing
  policy and short consent text, built from the real field inventory in
  `docs/DATA_INVENTORY.md`, not invented. Explicitly and repeatedly
  marked as a **draft requiring legal review** — jurisdiction isn't even
  determined in the document (first placeholder to fill in). **Not wired
  into the live bot/registration flow** — showing unreviewed
  legal-sounding text to real users as if it were the actual policy
  would be worse than the current honest gap, and changing what
  real people see during registration without the owner's sign-off
  isn't a call a technical assistant should make unilaterally.
  `consent_service.CURRENT_POLICY_VERSION` stays the placeholder
  (`"unset-v1"`) until the owner approves real text — swapping it is a
  one-line change once that happens.
- Verification: `pytest -q` full suite re-run, `ruff`/`compileall` clean,
  no migration in this PR.

### PR 21 — Live Menu Button Investigation: the Real Root Cause (merged)

Branch: `era-platform-pr21-live-menu-button-fix`. The owner reported that,
after PR20's deploy, nothing visibly changed for a real user in Telegram.
Rather than re-asserting deploy success, this block re-investigated from
scratch, and found a real bug PR20 did not touch.

**Root cause, found by reading actual router registration order, not
assumed**: `app/bot.py::create_dispatcher` registers `emergency.router`
*before* `start.router` (confirmed intentional — there's a pre-existing
test, `test_emergency_router_is_first`, asserting exactly this). Aiogram
resolves an update against the *first* fully-matching handler across the
whole router tree, in registration order, then stops. `emergency.py`'s
`rescue_start` is registered for `CommandStart()`/`Command("menu")` with
`StateFilter("*")`, which (confirmed by reading aiogram's own filter
source) matches unconditionally, for every state including none. This
means **`rescue_start` — not `start.py`'s more complete `start()` — is
what a real user's `/start` and `/menu` have actually been reaching all
along**, regardless of any of PR13–20's changes to `start.py`/`main_menu()`.

`rescue_start`'s call to `_send_main_menu()` never passed `settings`, and
`_send_main_menu()` renders `main_inline_keyboard()` — a *different*
keyboard from `main_menu()` (the one with the Mini App reply-keyboard
button, tested since the original 12-PR plan) — which had **no Mini App
button of any kind**, chat-menu-button fix or not. This is why PR20's fix
was invisible: the actual code path serving real `/start` never had a
button to begin with.

- Fixed `main_inline_keyboard()` (`app/keyboards/participant.py`) to
  accept `miniapp_url` and add the same "🔥 Открыть ЭРА" `web_app` button
  `main_menu()` already had. Threaded `settings` through every caller of
  `_send_main_menu()`: `emergency.py` (`rescue_start`, `cancel_any`,
  `rescue_menu_button`), `navigation.py` ("🧭 Главное меню"),
  `commands_ready.py` (`/menu`).
- **Startup self-verification** (`app/webapp.py`): after
  `setChatMenuButton`, calls `getChatMenuButton` and compares against
  what was requested via new `_menu_button_matches()` — logs ERROR (not
  just assumed success) on any mismatch, INFO with the bot's real
  username on success. New `/diag` HTTP endpoint exposes the cached
  result (`bot_username`, `menu_button_type`, `menu_button_verified`,
  `miniapp_configured`, `webhook_host` — no tokens/secrets) so this can
  be checked externally via `curl`, without `BOT_TOKEN` or a Telegram
  session.
- **Extended `/version` admin bot command** (`app/handlers/admin/
  version_command.py`) with live checks: `bot.get_me()`,
  `bot.get_chat_menu_button()`, `bot.get_webhook_info()`, and a real `SELECT
  1` — the same diagnostic surface, reachable from inside Telegram by an
  admin.
- **Investigated and ruled out** (not assumed) a per-chat menu-button
  override: searched the entire codebase and its full git history for
  any `set_chat_menu_button` call with an explicit `chat_id` — none
  exists, anywhere, ever. The global default is genuinely the only
  configuration that has ever been set.
- **Confirmed single source of truth**: only `app/webapp.py` calls
  `set_chat_menu_button`/`set_my_commands`. New
  `tests/test_chat_menu_button.py::SingleSourceOfTruthTests` enforces
  this going forward by parsing (not grepping) every file under `app/`.
- New regression test
  (`tests/test_fsm_global_recovery.py::test_rescue_start_real_menu_includes_miniapp_button`)
  calls `rescue_start` **without** mocking `_send_main_menu` away — the
  only test in the suite that exercises the actual router-selected
  handler end to end — and asserts the real reply contains the Mini App
  button. This is the one test that would have caught the original bug;
  every other existing test mocked `_send_main_menu` out entirely.

**What this does not and cannot prove from this environment**: that a
real Telegram client visually shows the button — verifying that requires
either the owner's own check or a connected browser session (see PR18c's
same limitation). What it does prove, with evidence gathered by actually
reading router source and aiogram's filter implementation rather than
re-running the same checks and hoping for a different answer: the code
path a real `/start` actually executes now includes the Mini App button,
where before this PR it structurally could not have, no matter what
`main_menu()` itself looked like.

### PR 22 — The Actual Final Blocker, Found by PR21's Own Diagnostics (merged)

Branch: `era-platform-pr22-menu-button-verification-fix`. Minutes after
PR21 deployed, its own new `/diag` endpoint was queried for real
confirmation — and it surfaced the true, final answer:

```
GET /diag →
{"commit":"8eb0404","bot_id":8481922061,"bot_username":"ERA_1bot",
 "menu_button_type":"commands","menu_button_verified":false,
 "miniapp_configured":false,"webhook_host":"https://era-telegram-bot.onrender.com"}
```

**`"miniapp_configured": false` on the real production service.**
`Settings.effective_miniapp_url` (`app/config.py`) returns `""` whenever
`MINIAPP_AUTH_SECRET` (or an explicit `MINIAPP_URL`) isn't actually set
— by design, to avoid shipping a button that opens a broken Mini App.
This means the Mini App button has been absent **in every form at once**
(chat menu button, `main_menu()`'s reply-keyboard button, PR21's
`main_inline_keyboard()` fix) not because of any code bug, but because
this one environment variable is missing on the real Render service.
`docs/DEPLOYMENT_RUNBOOK.md` had already documented this exact risk back
in PR13 as a *theoretical* caveat (`render.yaml`'s `generateValue: true`
only applies on Blueprint sync, not a normal deploy) — PR22 is that
theoretical risk **empirically confirmed** against the live service,
using the diagnostic tooling PR21 built specifically to stop guessing.

- Fixed a real false-positive discovered in the same `/diag` output:
  `menu_button_verified: false` even though nothing was actually wrong —
  `_menu_button_matches()` treated Telegram's own normalization of
  `default` → `commands` (confirmed real behavior: a bot with registered
  commands reports `commands` back for an unset menu button) as a
  mismatch. Only a real, requested `web_app` button not being honored is
  now flagged as an error.
- `docs/DEPLOYMENT_RUNBOOK.md` updated with the confirmed (not
  theoretical) finding and the exact one-step fix: set
  `MINIAPP_AUTH_SECRET` in Render Dashboard → Environment for
  `era-telegram-bot`, or sync the Blueprint. Verifiable afterward via
  `curl https://<host>/diag` → `"miniapp_configured": true`.
- Tests added for the normalization fix
  (`tests/test_chat_menu_button.py`).

**This is the actual, final, root-cause answer to "why doesn't the
button show up"**: PR21's router-shadowing fix was real and necessary
(without it, the button would still be missing even once this variable
is set), but this missing environment variable is what has kept the
button hidden through every prior deploy, and it is **outside this
environment's reach** — no Render dashboard access exists here. One
concrete action item for the owner, stated precisely, not guessed at.

## PR 23 — Mini App Live Sync: no more "press /start again" (merged)

Reported live by the project owner right after PR22's `MINIAPP_AUTH_SECRET`
fix went in: a participant who finishes registration (or is approved) sees
**no change in an already-open Mini App** — it just tells them to go press
`/start` in the bot again, which feels broken even though nothing is
technically wrong server-side.

**Root cause, found by reading the actual auth flow rather than guessing**:
`useAuth.ts` checked auth exactly once, on the very first mount. Telegram
clients frequently keep a Mini App's WebView alive in the background instead
of reloading it every time it's reopened from the chat menu button — so a
status change that happens while the app is backgrounded (an admin
approving the application, or the participant finishing registration in the
bot a moment after opening the Mini App) is never picked up. Two dead-end
screens made this worse:

- `PendingScreen` literally instructed the user to "open ERA again after
  that" — pure manual polling by the human, with no actual mechanism behind
  it.
- `AuthErrorScreen` (shown for `user_not_registered`/`401`/other auth
  failures) had no way to retry at all short of fully closing and reopening
  Telegram.

**Fix** (`frontend/src/hooks/useAuth.ts` rewritten, no backend changes
needed — `GET /api/v1/me` already existed and is exactly the lightweight
recheck this needed):

- Re-checks auth automatically whenever the WebView regains focus/visibility
  (`visibilitychange` + `focus` listeners), not just on first mount.
- While `application_status` is `pending`/`needs_info`, polls
  `GET /api/v1/me` every 15s (only while the tab is visible) so an approval
  is picked up on its own, no user action required.
- The re-check itself is cheap and safe: it reuses the existing session
  token against `/api/v1/me` first, only falling back to a full
  `POST /miniapp/auth` (re-verifying Telegram `initData`) if the token
  actually expired — avoids replaying stale `initData` unnecessarily.
- A transient failure (offline, 5xx) during a background re-check no longer
  downgrades a working screen to an error — only a real 401 triggers
  re-authentication, everything else just keeps showing what's already on
  screen.
- `PendingScreen` and `AuthErrorScreen` both gained a real "Обновить" /
  "Проверить сейчас" button wired to the same `refresh()`, so there's always
  a manual escape hatch too, not just silent polling.
- `StatusBanner` (shared by both screens, and others) gained an optional
  `actionLabel`/`onAction` button.

**Test**: `frontend/e2e/pending_sync.spec.ts` — a real, two-session
end-to-end proof, not a unit-level mock: a pending applicant's Mini App page
is opened once and never reloaded; a second, independent admin session
approves them through the real UI; back on the applicant's still-open page,
clicking "Проверить сейчас" (the same path the automatic listeners use)
flips it straight to the Home screen. This is the exact scenario reported
live, reproduced and proven fixed end-to-end.

**Scope note**: this fixes the pending→approved and any other
already-registered status transition. Opening the Mini App from the
persistent chat-menu button *before* a brand-new user has ever started
registration still correctly shows `AuthErrorScreen`'s "откройте бота и
нажмите /start" message (there is genuinely no user row yet) — now with a
working "Обновить" button to retry immediately after they do, instead of a
dead end.

## PR 24 — Admin Mode: People directory + profile actions (merged)

**Owner request**: "функций не хватает в админ панели тоже, которые были в
боте... админ панель главное исправь" — the Mini App's Admin Mode covered
registration applications, project/event moderation, task-submission
review, and offer-application review, but had **no equivalent at all** of
the bot's `admin:participants` flow: searching/browsing every user (not
just pending applications), viewing a full profile card, changing role,
blocking/archiving, granting technical permissions, or awarding points/a
badge directly. This was the single largest capability gap between the bot
and the Mini App's admin surface.

**Backend**: `app/services/user_management_service.py` (new) — extracted
from `app/handlers/admin/rights_block6.py` and
`app/handlers/admin/user_profile_block3_safe.py` without changing either
bot handler's behavior: `search_users` (name/username/Telegram-ID search +
role filter + pagination, backing the directory), `change_role`,
`set_blocked`, `set_archived` (all reusing `authorization_service`'s
existing decision functions — same "can't demote the last admin", "can't
touch your own access" rules as the bot), `toggle_permission`,
`award_points`, `award_badge` (mirrors the bot's amount/reason flow exactly,
including the `-10000..10000` range rule).

**API**: `app/api/v1/admin.py` — `GET /admin/users` (search+paginate),
`GET /admin/users/{id}` (full profile: contact fields, balance, portfolio
count, owned/available badges, per-permission map, social links, and
`can_manage`/`can_manage_permissions`/`can_award_points` flags so the
frontend renders exactly the actions the current admin is allowed), plus
`POST .../role`, `.../block`, `.../archive`, `.../permissions/{permission}`,
`.../points`, `.../badges/{badge_id}` — each behind its own guard
(`can_view_people` / `can_manage_people` / `can_manage_permissions`, or the
bot's own `points.award`-specific rule for points/badges — narrower than
`people.manage` on purpose) and the same `enforce_admin_action_rate_limit`
already covering every other Admin Mode mutation.

**Frontend**: new "Участники" tab in `AdminScreen` →
`AdminUsersScreen`/`PeopleList`/`PersonDetail` — search + role filter list,
tap through to a full card with role selector, block/archive buttons,
permission checkboxes, and a points/badge award form, each section only
rendered if the current admin's `can_*` flags allow it.

**Tests**: `tests/test_user_management_service.py` (14, real SQLite DB —
search filters, role/block/archive authorization decisions, permission
grant create-vs-toggle, points balance math, badge award idempotency),
`tests/test_admin_people_api.py` (23, guard boundaries + happy path + one
conflict per mutating endpoint), `frontend/e2e/admin_people.spec.ts` (real
stack: admin searches the directory, opens a seeded participant, awards
points, sees the refetched balance).

**Known limitation carried forward**: partner-offer CRUD (creating/editing
offers, not just reviewing applications to them), auctions, surveys, and
per-event participant/attendance management — all bot-only via
`app/handlers/admin/partners_admin.py`, `auction_block17.py`,
`surveys_analytics.py`, `event_registration_block14.py` — remain
unported; People management was the highest-impact single gap and is
covered first. Visual redesign of the Mini App is tracked separately (see
next section / owner request in this same message).

## PR 25 — Admin/Project operations: events, team-search posts, partner catalog (merged)

**Owner request**: continue the bot-vs-Mini-App admin audit — "для админа
и проекта все проанализируй что было в боте... необходимо добавить" — and
close the next three gaps found.

**Event operations** (`app/services/event_registration_service.py`):
`list_operational_events` (events already approved/published, distinct
from the moderation queue), `list_participants`, `set_attendance`,
`award_attendance_points` — mirrors
`app/handlers/admin/event_registration_block14.py` exactly, including its
idempotency key, so re-running an award after marking one more attendee
never double-pays anyone already paid.

**Project "looking for a team" posts** (`app/services/project_workflow_service.py`):
`team_post_state`, `list_projects_with_pending_team_post`,
`prepare_team_post`, `edit_team_post`, `reject_team_post`,
`publish_team_post` — mirrors `app/handlers/admin/projects_block5_team.py`'s
approve/edit/reject/publish flow exactly, including its storage as two keys
inside the existing `form_data` JSON blob rather than a new column, so the
Bot and the Mini App can't drift into two different ideas of a post's
state. Deliberately distinct from ProjectWorkspace's in-app roles/
applications system (PR 5): this broadcasts to the general Telegram chat,
reaching people who aren't necessarily browsing the Mini App at all —
investigated and confirmed both mechanisms are still live and
non-overlapping before porting this, not assumed redundant.

**Partner + offer catalog** (`app/services/opportunity_service.py`):
`list_partners`, `create_partner`, `set_partner_active`, `archive_partner`,
`list_offers_admin`, `get_offer_with_partner`, `create_offer`,
`set_offer_active`, `archive_offer` — mirrors
`app/handlers/admin/partners_admin.py` and the create/list/toggle/archive
half of `partner_offers_block16.py`. The Mini App's existing
offer-application review (PR 12) only ever covered reviewing participants'
applications to offers that already existed; there was no way to create or
manage a partner or an offer itself without the Bot.

**API**: 17 new endpoints on `app/api/v1/admin.py` (5 team-post, 4 event
ops, 4 partner CRUD, 4 offer CRUD), each behind its existing area's guard
(`require_project_reviewer` / `require_event_reviewer` /
`require_offer_reviewer`) and the existing admin action rate limit.

**Frontend**: `AdminProjectsScreen`, `AdminEventsScreen`, and
`AdminOffersScreen` all split into sub-tabs via `PillTabs` — moderation
queue vs. team-posts; moderation queue vs. live-event
participants/attendance; applications vs. offers vs. partners — so the new
operational actions sit next to, not instead of, the existing moderation
screens.

**Tests**: `test_event_registration_service.py` (3, new), team-post
additions to `test_project_workflow_service.py` (8), partner/offer CRUD
additions to `test_opportunity_service.py` (8), `test_admin_operations_api.py`
(28, new — guard boundaries + happy path + one conflict per endpoint),
`frontend/e2e/admin_catalog.spec.ts` (real stack: admin creates a partner,
then an offer for it, sees both appear from the refetched list).

**Not yet ported** (real gaps, not oversights — flagged for a follow-up
PR before any Bot admin code is removed, per the owner's "очистить бота от
дублей" request): auctions (`auction_block17.py`), surveys and analytics
export (`surveys_analytics.py`, `analytics_filters.py`), office/department
assignment (`offices_management.py`). Deleting the Bot's admin handlers for
these now — before a Mini App equivalent exists — would be a feature
regression, not cleanup, so the Bot-cleanup pass is sequenced to happen
only after every admin capability has a working Mini App counterpart.

## PR 26 — Admin: "Должности и ответственность" (offices) (merged)

Closes the office/department-assignment gap flagged in PR 25. Ported
without changing behavior — this feature is split across two Bot files
(`app/handlers/admin/offices_management.py` for list/view/delete,
`office_assign`/`office_remove`/`office_new` in `panel.py` for the
assignment flow) and was investigated as one cohesive feature rather than
assumed to be two separate ones or dead code shadowing each other (unlike
the router-precedence bug found in PR21) — both files' handlers are live
and simply divide the work.

**Backend** (`app/services/office_management_service.py`, new):
`list_offices`, `create_office`, `list_assignments`,
`search_assignable_users` (mirrors `panel.py::office_assign_find`'s name/
username/Telegram-ID search exactly), `assign_office` (idempotent — a
second assignment attempt for the same person is a no-op, matching the
Bot's own de-duplication check), `remove_assignment`, `delete_office`
(soft-delete: ends every active assignment and writes the same audit
entry as the Bot's `office_delete`).

**API**: `GET/POST /admin/offices`, `POST /admin/offices/{id}/delete`,
`GET /admin/offices/assignable-users`, `POST /admin/offices/{id}/assign`,
`POST /admin/offices/assignments/{id}/remove` — all behind
`require_people_manager` (`can_manage_people`), matching the Bot's own
guard on both files' handlers.

**Frontend**: new "Должности" tab in `AdminScreen` → `AdminOfficesScreen`
— create a position, see current assignees inline, search-and-assign a
person, end an assignment, delete a position.

**Tests**: `test_office_management_service.py` (7, real SQLite DB),
`test_admin_offices_api.py` (11, guard boundaries + happy path + one
conflict), `frontend/e2e/admin_offices.spec.ts` (real stack: admin creates
an office, assigns the seeded participant, sees the assignment appear).
`test_admin_leader_rate_limiting.py`: updated hardcoded admin POST route
count (25 → 29).

**Remaining before the Bot admin-cleanup pass**: auctions and surveys/
analytics export are still Bot-only.

## PR 27 — Points-based auctions, participant + admin (merged)

Closes the auctions gap flagged in PR 25/26 — the last participant-facing
feature (not just an admin one) that existed only in the Bot. Ported both
halves: `app/handlers/participant/auction_block17.py` (browse, bid) and
`app/handlers/admin/auction_block17.py` (create a lot, confirm the winner,
mark delivered, cancel).

**Backend** (`app/services/auction_service.py`, extended — the existing
pure formatting helpers `format_local`/`remaining_time`/`bidder_name`/
`top_bid_with_user`/`is_open` are untouched): `next_minimum_bid`,
`list_active_auctions`, `list_all_auctions`, `get_user_bid`, `list_bids`,
`place_bid` (same minimum-bid and balance checks, same upsert-by-user
semantics as the Bot — a bid never touches points, only a confirmed win
does), `create_auction`, `confirm_winner` (walks bids highest-first, skips
— marks invalid — any bidder blocked/archived/short of balance since
bidding, deducts points only from the actual winner, marks every other
bid "lost"; mirrors the Bot's handler exactly, including its idempotency
key), `mark_delivered`, `cancel_auction`.

**API**: new `/api/v1/auctions` router (participant-facing: list/detail/
bid, no role restriction beyond being an approved user — same as the
Bot); `app/api/v1/admin.py` gains `GET/POST /admin/auctions`,
`POST /admin/auctions/{id}/confirm-winner`, `.../deliver`, `.../cancel`,
all behind `require_offer_reviewer` (`can_manage_partners`), matching the
Bot's own `admin_ok` guard.

**Frontend**: new "Аукционы" tab in `OpportunitiesScreen` (participant —
browse lots, see the current top bid/leader, place a bid) and in
`AdminOffersScreen` (admin — publish a lot, confirm winner/cancel once
bidding closes, mark delivered).

**Tests**: `test_auction_service.py` (11, real SQLite DB — including the
"blocked bidder is skipped, runner-up wins" and "nobody qualifies" edge
cases the Bot handler itself handles), `test_auctions_api.py` (14, both
routers), `frontend/e2e/auctions.spec.ts` (real stack: admin publishes a
lot, a dedicated seeded bidder places a real bid, sees it reflected after
the refetch). `scripts/e2e_seed.py` gained a dedicated
`AUCTION_BIDDER_TELEGRAM_ID` (900006) with a pre-seeded 1000-point
balance — kept separate from the shared participant fixture (900001) so
`admin_people.spec.ts`'s exact post-award balance assertion never has to
account for points spent bidding elsewhere.
`test_admin_leader_rate_limiting.py`: updated hardcoded admin POST route
count (29 → 33).

**Remaining before the Bot admin-cleanup pass**: surveys/analytics export
(`surveys_analytics.py`, `analytics_filters.py`) is the only Bot-only
admin capability left. Once it's ported, every admin (and now every
participant-facing) capability will have a Mini App equivalent, and the
Bot-cleanup pass — removing the now-duplicated Bot handlers — can begin.

## Progress vs. the 12-PR plan

- **Completed: 12 of 12 full PRs merged** (PR 1 + PR 1b deploy
  follow-up + hotfix; PR 2; PR 3; PR 4; PR 5 Project Workspace,
  delivered through PR #114, PR #115 and PR #116; PR 6 Opportunities;
  PR 7 Admin Mode foundation; PR 8 Profile + Portfolio; PR 9 Leader
  Mode foundation; PR 10 Admin Event Moderation; PR 11 Admin Task
  Submission Review; PR 12 Admin Opportunity Application Review), plus
  the unnumbered PR #122 Mini App design polish pass.
- The original 12-PR plan is now complete. The Mini App covers Home,
  Activity (Events/Tasks/Calendar/History), Projects + Project
  Workspace, Opportunities, Profile + Portfolio, Leader Mode (scope
  overview + open tasks), and Admin Mode (dashboard, registration
  applications, project/event moderation, task-submission review,
  offer-application review) — all built by extracting/reusing the
  Bot's existing services, with the Bot itself unchanged in behavior
  throughout.
- Remaining work is the accumulated "Known limitation" backlog from
  PR 7 through PR 12 (see each section above) rather than anything from
  the original numbered plan — future sessions should treat that
  backlog, plus any new brief from the project owner, as the source of
  truth for what comes next.
