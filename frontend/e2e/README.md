# E2E tests

Real end-to-end tests: a real FastAPI backend, a real (throwaway) SQLite
database, and the actual production frontend build — served exactly as
`app/webapp.py` serves it in production, at `/app/`. No mocked API layer.

## Login without a real Telegram session

Real Telegram `initData` can't be produced outside a real Telegram client.
Instead, `useAuth.ts` reads an optional `?devTelegramId=<id>` query param and
forwards it to `POST /api/v1/miniapp/auth` as `devTelegramId`. The backend
only honors that field when `DEV_AUTH_ENABLED=true` — which
`Settings.assert_safe_for_deployment()` refuses to allow on a Render
deployment (see `docs/PRODUCTION_READINESS_AUDIT.md`, finding #2) — so this
is a no-op against the real deployed bot regardless of what a URL contains.

## Running locally

```bash
# 1. Build the frontend the server will actually serve.
cd frontend && npm run build && cd ..

# 2. Seed a throwaway SQLite DB with the fixture users/event these specs use.
DATABASE_URL="sqlite+aiosqlite:///./e2e.db" PYTHONPATH=. python scripts/e2e_seed.py

# 3. Start the real server against that DB (needs a local Redis for FSM storage).
DATABASE_URL="sqlite+aiosqlite:///./e2e.db" \
  BOT_TOKEN="0000000000:E2ETESTTOKEN" \
  MINIAPP_AUTH_SECRET="e2e-test-secret" \
  DEV_AUTH_ENABLED=true \
  REDIS_URL="redis://127.0.0.1:6379/0" \
  python -m uvicorn app.webapp:app --port 8000 &

# 4. Wait for it, then run the specs.
curl --retry 10 --retry-delay 1 --retry-connrefused http://127.0.0.1:8000/health
cd frontend && npx playwright test
```

CI (`.github/workflows/ci.yml`, `e2e` job) runs exactly this sequence with a
`services: redis` container.

## Fixtures

Seeded by `scripts/e2e_seed.py`, fixed Telegram IDs so specs can reference
them directly: participant `900001`, leader `900002`, admin `900003`, and a
`900004` pending applicant for the admin-approval scenario. One future,
`registration_open` event so the participant spec has something to
register for.

## Scope

One scenario per role, each exercising a real state change through the full
stack (not just a page render):

- **Participant** (`participant.spec.ts`): logs in, sees the Home greeting,
  opens Activity → Events, registers for the seeded event, sees the
  registration reflected in the UI.
- **Leader** (`leader.spec.ts`): logs in, opens the open-tasks tab, creates
  a new open task through the real form, sees it appear in the list.
- **Admin** (`admin.spec.ts`): logs in, opens Applications, approves the
  seeded pending applicant, sees them disappear from the pending queue.

Not covered here (see `docs/PRODUCTION_READINESS_AUDIT.md` backlog):
concurrent-decision races, file/portfolio upload, and the chat/registration
scenarios covered separately by the addendum's live-checklist re-verification.
