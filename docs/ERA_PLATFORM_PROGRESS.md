# ERA Platform — progress

Single source of truth for the Bot + Mini App platform build-out. Read this
file first in every new session, then `git status` / `git log -1`, then only
the files touched by the current block. Do not re-audit the whole repo.

## Baseline

- Current `main` commit: `1a040973a9782264e01f940998ad4b34c6a0c9a5` (PR #108 merge,
  fast-forward).
- Previous base commit: `36098e985e407f806f7a0134dafc36152a9f71a8` (origin/main,
  PR #107 merge).
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

**Next block:** PR 2 — design system + bottom navigation + Home screen
(rule-based "next step" recommendation) + Growth Level display, per
section 7.1 of the platform brief.

## Progress vs. the 12-PR plan

- Completed: 1 of 12 full PRs merged (PR 1 — foundation, plus its PR 1b
  deploy follow-up).
- Current stage: PR 2 — design system, navigation, Home, Growth (not started).
- Next stage after PR 2: PR 3 — Activity (Events, Tasks, Calendar, History).
