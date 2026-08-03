# ERA Platform — progress

Single source of truth for the Bot + Mini App platform build-out. Read this
file first in every new session, then `git status` / `git log -1`, then only
the files touched by the current block. Do not re-audit the whole repo.

## Baseline

- Confirmed base commit: `36098e985e407f806f7a0134dafc36152a9f71a8` (origin/main,
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

- `MINIAPP_URL` — https URL of the deployed Mini App frontend (BotFather
  Web App URL). Until set, the bot works exactly as before (no button
  appears).
- `MINIAPP_AUTH_SECRET` — random secret used to sign Mini App session
  tokens. Until set, `/api/v1/miniapp/auth` returns 500
  `miniapp_auth_not_configured` rather than issuing an unsigned/insecure
  token.
- `BOT_USERNAME` — used later for bot deep-link helpers (PR building
  `miniapp_link()` / `task_submit:<context>` helpers); not required for PR 1.
- `PUBLIC_BASE_URL` — already existed before this platform work; unchanged.

## PR log

### PR 1 — ERA Platform foundation (in progress)

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

**Next block:** PR 2 — design system + bottom navigation + Home screen
(rule-based "next step" recommendation) + Growth Level display, per
section 7.1 of the platform brief.

## Progress vs. the 12-PR plan

- Completed: 0 of 12 full PRs merged (PR 1 in progress in this session).
- Current stage: PR 1 — foundation.
- Next stage: PR 2 — design system, navigation, Home, Growth.
