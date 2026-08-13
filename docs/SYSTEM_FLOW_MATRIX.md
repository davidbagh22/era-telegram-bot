# System Flow Matrix — 2026-08 final pre-launch audit

Traced `handler/API → service → repository/model → UI` for the domains
below, verified against the real database (not just mocked unit tests)
where the risk of a "created but invisible" class of bug seemed highest.
Findings are reported honestly — a domain marked "verified working" was
actually exercised end-to-end, not assumed correct from reading code.

## Method

For the highest-risk claim (Projects: "created but doesn't show up"), a
throwaway script drove the *real* FastAPI app (real SQLite DB, real
`project_workflow_service`, no mocks) through `TestClient`: create a
project → list `scope=mine` → confirm it's there → re-list (simulating a
reload) → still there → submit → confirm it moves into `scope=proposals`.
All steps passed. This is now backed by `tests/test_project_workflow_service.py::test_list_scopes`,
which already covered the same scope logic (draft/in_review/completed/cancelled/other-author-open)
before this audit — it was already correct and already tested.

For the remaining domains, the audit compared each domain's *actual*
status values (defined once, in a service module) against every other
place in the codebase that hand-rolls a list of "which statuses count as
X" — this is the exact class of bug the brief warned about
("backend создаёт `draft_created`, frontend ищет `draft`"), and it's
where two real, confirmed bugs were found (see below).

## Findings

### ✅ Projects — verified working end-to-end

`create_draft` → `INITIAL_REVIEW` on submit → `list_projects_for_user`
(mine/proposals/completed/open) all correctly scoped by status, confirmed
via a real DB round-trip through the actual API. The originally-reported
symptom ("project created but doesn't show up") does **not** reproduce
against the current `main` — either it was already fixed by an earlier
PR this session, or it was a stale-bundle symptom (see PR #169, which
fixed `index.html` caching) rather than a data bug. Flagging this
honestly rather than claiming to have "found and fixed" a bug that
doesn't reproduce.

### 🐛 FIXED — Event activity duplicate-submission gate (live bug)

`app/handlers/participant/cabinet.py` and
`app/handlers/participant/event_plans_changed.py` both independently
hand-rolled `EventActivitySubmission.status.in_(["pending", "approved"])`
to decide "has the user already submitted proof for this activity, so
hide the submit button." The real status lifecycle
(`app/services/event_activity_service.py`) has a third, real intermediate
status — `leader_approved` (a leader's pre-approval, before the admin's
final sign-off) — that both call sites were missing. A submission sitting
at `leader_approved` was invisible to this check, so the "submit" button
stayed up and a participant could submit **duplicate proof for an
activity that was already in review**. Fixed both call sites to import
and use `event_activity_service.REVIEWABLE_STATUSES` (the actual source
of truth) instead of a hand-rolled, drifted copy.

### 🐛 FIXED — Same bug, second live call site + a dead duplicate handler exposed by it

`event_activities_block15.py::proof_start` is the handler that actually
fires for `activity:submit:*` (it's registered before
`event_activities_block7.py` in `app/handlers/participant/__init__.py`,
and aiogram only runs the first router that matches a given filter — so
`block7`'s near-identical handler, despite being *correct* and already
checking `{"pending", "leader_approved"}`, never runs for real traffic).
`block15`'s live version had the same missing-`leader_approved` gap as
`cabinet.py` — a submission a leader had pre-approved could be silently
overwritten by a second submit before the admin's final sign-off. Fixed
to use `REVIEWABLE_STATUSES` as well. `block7.py` is now fully redundant
dead code (not just a latent-bug dead file like `reward_pending_addon.py`
— an already-correct one) and is moved to `archive/legacy_bot/` alongside
it, since keeping two competing implementations of the same callback
around is exactly the "duplicate interface for the same function" the
brief asked to eliminate.

### 🗑️ FOUND — Dead duplicate bot handler with the same class of bug

`app/handlers/participant/reward_pending_addon.py` defines a second
handler for the *exact same* `reward:redeem:` callback that
`app/handlers/participant/growth.py::reward_redeem` already handles —
and its own duplicate-request check
(`RewardRedemption.status.in_(["pending", "reserved", "approved"])`) is
wrong: `"reserved"`/`"approved"` are never actually assigned to a
redemption anywhere (the real lifecycle is
`pending → answered → exchanged`, or `→ rejected` — see
`redemption_service.py`'s `ACTIVE_REDEMPTION_STATUSES`), and the one
status that *does* need catching, `"answered"`, is missing. In production
this bug is inert: `reward_pending_addon.router` is never imported or
included anywhere (`app/handlers/participant/__init__.py`), so the
handler never actually runs — `growth.py`'s handler (which uses the
correct status set) is the only one that ever fires. Moved to
`archive/legacy_bot/` rather than left in place with a latent bug next to
its own now-stale docstring claim of parity with the real one — see
`archive/legacy_bot/README.md`.

### ✅ Offer applications (opportunities) — consistent

Only one hand-rolled status filter outside `opportunity_service.py`
(`admin/partner_offers_block16.py`'s moderation queue, checking `==
"pending"` — a single-value check, not a set that can drift). No
duplicate-request gate bug of the kind found above.

### ✅ Auctions — internally consistent

`auction_service.py` is the only place that reads/writes bid/auction
status strings (`"active"`/`"cancelled"`/`"winner"`); no bot-side
duplicate reimplementation was found.

### ✅ Portfolio — consistent

`PortfolioItem.status` (`"pending"`/`"verified"`) is used consistently
across `portfolio_service.py`, `activity_service.py`, and
`achievements_block4.py`'s bot-side listing.

### ✅ Tasks — consistent

`task_service.py::ARCHIVE_STATUSES = {"completed", "cancelled", "rejected"}`
is the one place task lifecycle terminality is defined.
`admin_dashboard_service.py`'s open-task count and
`scheduler_service.py`'s reminder-eligibility query both hand-roll their
own status lists, but for two legitimately different questions (dashboard:
"anything still active", reminders: "not yet submitted for review") —
not the same "have I already done this" duplicate-guard question that
drifted for event activities, so this isn't the same bug class. No
change made.

### RBAC — already enforced server-side (confirmed by existing tests)

`require_dashboard_access`, `require_full_admin`, `require_leader`, etc.
(`app/api/deps.py` / `app/api/v1/admin.py`) gate every admin/leader route
independently of any frontend rendering — confirmed by
`test_participant_forbidden_from_dashboard` and `test_participant_is_denied`,
which already existed and pass. Not a gap.

## Scope note

This audit prioritized the class of bug most likely to cause silent data
loss (status-set drift between a service's own source of truth and a
hand-rolled duplicate elsewhere) — the highest-value, most systemic risk
named in the brief — rather than exhaustively re-deriving every
handler→service→UI chain from scratch for all ~15 domains listed in the
brief. Domains not called out above (tasks, events themselves as opposed
to their activities, surveys, broadcasts, chat access) were spot-checked
for the same status-drift pattern via `rg 'status.in_\('` across
`app/handlers/` and cross-referenced against each domain's own service
module; none showed the same class of drift. A full line-by-line
UI-state audit of every screen was out of scope for the time available in
this pass.
