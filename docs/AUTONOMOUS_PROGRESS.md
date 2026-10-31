# ЭРА — автономная разработка

Updated: 2026-10-30 UTC. This is the primary continuation point for the hourly task
`6adcbd42ede08191a5c0a946e4147b52` («ЭРА — разработка до полной готовности»).
Read this first, then current main/PR/CI/Render; consult older AI_TASK_STATE.md and
checkpoint documents only for evidence relevant to the selected task. Do not restart
the audit or create another automation. Existing task updated with the user's full
30 October autonomous-development requirements, hourly, Asia/Yerevan.

## Release and current change

- Initial 30 October checkpoint main/LIVE: `1a8b635792e0b931e079d99dde380bd1a2ffe706`; see the newest dated entry below for current exact SHAs.
- Render deploy `dep-dbie8l29lscs73f7m3n0`, LIVE 2026-10-30 18:40:25 UTC.
- Infrastructure: davidbagh22/era-telegram-bot; Render workspace
  `tea-d91quq1o3t8c73ehphh0`, service `srv-d91r1j7avr4c73fs8h00`;
  https://era-telegram-bot.onrender.com; @ERA_1bot. @MVKSRS_bot is separate.
- Current branch: `fix/profile-remove-path-autonomous-state-20261030`.
- Change: remove profile growth ladder «Мой путь», its criteria and stage counter;
  retain points, contributions, portfolio, vector and participation history. Rename
  «Лента пути» to «История участия». Update existing portfolio browser regression
  to check the requested absence while still verifying earned-badge navigation.
- Files: frontend/src/screens/ProfileScreen.tsx, frontend/e2e/portfolio.spec.ts,
  docs/AUTONOMOUS_PROGRESS.md. CI/release pending when this checkpoint was written.
- Next: complete exact-head PR CI (six jobs), merge with expected_head_sha, check
  main CI and automatic Render LIVE exact merge SHA, run production_readonly_smoke.
  Then implement safe hiding from public event listings and published-poster editing
  using existing event administration; inspect existing visibility/history policies
  and drafts #484/#486 before changing them. Never delete registrations or history.

## Acceptance register (40 stable requirements)

Status is NOT a subjective completion percentage. ПРОВЕРЕНО requires code/tests,
main/LIVE and actual relevant user scenario evidence. ВЫПУЩЕНО alone does not close
acceptance. Grouped requirements below require ALL their listed parts; split them
only with an explicit register revision explaining the changed denominator.
Current strict acceptance: 1/40 = 2.5%; 39 remain open. This measures evidenced
acceptance, not the fraction of existing code. No new real Telegram acceptance
was performed in this run. Historical proof must retain its date.

| ID | Requirement | Status | Remaining evidence / action |
|---|---|---|---|
| A01 | Registration and authorization full cycle | ВЫПУЩЕНО | Real fresh/resumed application, photo, approval and login |
| A02 | Roles and access boundaries | В РАЗРАБОТКЕ | #542; real admin/leader/employee/participant matrix |
| A03 | Convenient main menu | ВЫПУЩЕНО | Verify final mobile navigation and legacy keyboard |
| A04 | Remove «Мой путь» from profile | ВЫПУЩЕНО | #586 main CI 5/5, Render LIVE exact `ece02e9`; real profile iPhone/Android acceptance unconfirmed |
| A05 | Buttons, typography and logo | В РАЗРАБОТКЕ | Mobile visual review against agreed design |
| A06 | iPhone and Android Mini App | В РАЗРАБОТКЕ | Real Telegram clients, not only Playwright |
| B01 | Event create/publish/edit | ВЫПУЩЕНО | Real authorized scenario, no test announcement |
| B02 | Edit published event poster | ВЫПУЩЕНО | #587 main/Render LIVE exact ed5a6f5; real admin iPhone/Android acceptance not confirmed |
| B03 | Hide/remove events from general poster listing | В РАЗРАБОТКЕ | DRAFT #589, requires CI/PG migration/owner privacy policy and real acceptance |
| B04 | Publication latency and duplicate prevention | В РАЗРАБОТКЕ | #447 shipped; legacy #467/#491, uncertain receipts |
| B05 | Registration, waitlist, capacity and deadlines | В РАЗРАБОТКЕ | Review overlapping #507/#510/#514/#515 as coherent package |
| B06 | QR attendance | ВЫПУЩЕНО | Real scoped confirmation and repeated-scan acceptance |
| B07 | Event points | ВЫПУЩЕНО | Actual attendance-to-ledger evidence, no test balance edits |
| B08 | Actual production event list | В РАЗРАБОТКЕ | Authenticated read unavailable; do not invent the list |
| C01 | Media chat and all eight topics | ВЫПУЩЕНО | Oct27 topics=8, pinned navigation8455; current role/link check |
| C02 | Agreed media recruitment notification | ПРОВЕРЕНО | #429; Oct26 18:09:42Z sent message26588; receipt reuse, no resend |
| C03 | Media content plan and calendar | В РАЗРАБОТКЕ | #551 malformed metadata/scoped privacy; role acceptance |
| C04 | Media tasks and staff | В РАЗРАБОТКЕ | Complete assignment/review and scoped membership acceptance |
| C05 | Media materials and knowledge | ВЫПУЩЕНО | Knowledge base shipped; real upload/edit/access scenarios |
| C06 | Media notices, rights and damaged records | В РАЗРАБОТКЕ | #468 reminders; navigation rebinding receipt review |
| D01 | Simple manager assignments | ВЫПУЩЕНО | #488 three fields and /team_tasks; real user cycle |
| D02 | Complete/review/return tasks | ВЫПУЩЕНО | Different people, no self-review or double points |
| D03 | Task files, deadlines and reminders | В РАЗРАБОТКЕ | Real files and scoped 24h/3h delivery acceptance |
| D04 | Task statuses and manager notifications | ВЫПУЩЕНО | Actual acknowledgements and visibility by role |
| D05 | Pulse complete cycle and reports | В РАЗРАБОТКЕ | #446 concurrency fix shipped; real questionnaire/report |
| D06 | Repair leaders panel | В РАЗРАБОТКЕ | #520 shipped; actual existing panel repair unconfirmed |
| E01 | Points and duplicate award protection | ВЫПУЩЕНО | Full ledger/review/retry acceptance |
| E02 | Projects and portfolio | ВЫПУЩЕНО | Real lifecycle and privacy, upload/view/delete policy |
| E03 | Analytics from real data | ВЫПУЩЕНО | Verify period/scope totals against authorized source |
| E04 | Monthly projects PDF | ВЫПУЩЕНО | Layout tested historically; real complete month delivery |
| E05 | Games and team mechanics | В РАЗРАБОТКЕ | Content/round/result acceptance; Mafia excluded |
| E06 | Literature club | ВЫПУЩЕНО | Real issue, subscription, discussion and reporting |
| E07 | FAQ and support | ВЫПУЩЕНО | Scoped handling, replies and privacy acceptance |
| E08 | My Vector | В РАЗРАБОТКЕ | Methods/check-ins/goals/history/privacy and earlier backlog |
| E09 | Daily quotes | ВЫПУЩЕНО | Actual daily receipts in Mini App/chat/channel as authorized |
| E10 | Broadcasts and notifications | В РАЗРАБОТКЕ | #491 incomplete receipts; no uncertain replay |
| E11 | Security and data protection | В РАЗРАБОТКЕ | #475/#484/#486/#542; auth and role checks |
| E12 | Backup and restore | ВЫПУЩЕНО | Encrypted GitHub + isolated PG restore evidenced; latest review |
| E13 | Legal/content organizational acceptance | В РАЗРАБОТКЕ | Draft #364 requires responsible human approval |
| E14 | Final multi-role production acceptance | НЕ НАЧАТО | All required scenarios, no known blockers, observation |

## Open technical work and CI

Open code/content drafts observed 30 October: #584 callback/FSM IDs; #578 durable
forum creation claim; #551 calendar metadata; #542 inactive admin denial; #537
corrupt attendance notices; #523 wizard JSON recovery; #515 capacity locks; #514
registration policy locks; #510 native waitlist parity; #507 commit before notices;
#500 malformed reminders; #491 incomplete broadcast receipts; #486 cancelled
event history; #484 public poster privacy/MIME; #475 webhook secret; #468 3h media
reminders; #467 legacy event publication; #364 legal. Their current HEAD CI needs
fresh verification before release. Older green runs never authorize changed HEADs.
Many additional open PRs are historical checkpoint documents; merging them does
not complete functional requirements. Do not blindly merge old docs over new state.

## Human blockers and non-negotiable constraints

- Authenticated Telegram/Mini App session and distinct real roles not available.
  Panel repair needs existing bot panel in the configured leaders topic and an
  authorized admin: /leaders_repair important as a reply, after verifying it.
  Do not manufacture panel receipts, messages, accounts or successful acceptance.
- PostgreSQL external allowlist is empty by design. Connector SQL cannot reach it;
  do not open it. Real event list needs an authorized application/secure internal read.
- Do not publish or resume «Траектория открытий», 31 October 2026, without new
  explicit user permission. Do not publish new ERA messages without concrete prior
  authorization. No mass tests or uncertain retries. No Mafia.
- No destructive migrations, deletion of user data or real points/participation
  changes for testing. No secrets in output. Respect dirty worktrees.
- Merge only reviewed exact HEAD with all required CI, then main CI and automatic
  Render checksPass. No manual deploy/bypass. CI/HTTP health != user acceptance.
- If a run hits platform limits, persist the next action and stop; never bypass
  limits. The next available hourly run continues here. No continuous execution
  between runs is promised.

## Reporting

Report only material results/blockers, usual window 09–19 Asia/Yerevan. One factual
daily summary; record its delivery date here when sent. Last daily summary under
this register: none yet. Format: «ЭРА | Автономная разработка», completed, evidence,
open count, accepted percentage, next concrete action. Never declare 100% until
all forty requirements are ПРОВЕРЕНО and all known mandatory backlog is closed.

## 2026-10-31 00:39 Asia/Yerevan — profile release and published-poster editor

- **Fresh GitHub main:** `ece02e943eba890cb7363a18c938b8070b45fa07` (merge PR #586, exact reviewed head `74c83a97db9fc30531c132de679f2192aa199a47`). PR #586 exact-head Bot checks five SUCCESS and Tests one SUCCESS; merge used `expected_head_sha`. Main push Bot checks run `41124158813`: secret-scan/frontend/postgres-migration SUCCESS, test/e2e IN_PROGRESS at last read. Do not mark main CI passed until all five succeed.
- **Render:** latest observed LIVE remains `1a8b635792e0b931e079d99dde380bd1a2ffe706`, automatic deploy `dep-dbie8l29lscs73f7m3n0` finished 2026-10-30 18:40:25 UTC. **New main is NOT yet confirmed LIVE.** Service `autoDeploy=yes`, `autoDeployTrigger=checksPass`; no manual deploy.
- **Profile:** PR #586 removes visible «Мой путь», growth ladder, criteria and stage count; preserves points, portfolio, contributions and My Vector; renames timeline to «История участия». Browser regression updated. **A04 remains В РАЗРАБОТКЕ** until exact main CI/LIVE and real profile device acceptance; no invented acceptance.
- **New independent feature DRAFT PR #587:** branch `feat/admin-published-poster-editor-20261031`, head `40b6a4aa60daf566077e5126d249e483a41d4794`. Adds admin-only published-poster edit from operational events, preview, validated JPG/PNG/WEBP ≤5 MB, explicit image-only removal confirmation, no event deletion, no publish, no registration/points changes or automatic messages. Browser test intercepts all poster/event writes and asserts no publish. Files: `frontend/src/screens/admin/events/EventPosterEditor.tsx`, `frontend/src/screens/admin/events/EventsList.tsx`, `frontend/src/screens/admin/AdminEventsScreen.tsx`, `frontend/e2e/event_poster_edit.spec.ts`. PR #587 Bot checks run `41124442221` and Tests run `41124442132` IN_PROGRESS at last read; no local full repository tests because container GitHub DNS unavailable. **B02 remains В РАЗРАБОТКЕ** until exact-head CI, release and real admin device acceptance.
- **Independent callback hardening:** PR #584 exact head `93219e9e6c20565da378a1bf7e82d1e475bc7d76` has Bot checks 5/5 and Tests 1/1 SUCCESS; source reviewed for bounded attendance/selfie/feedback callback and FSM IDs, with policy gap #585 unchanged. It remains DRAFT/unmerged; decide safe release only after #586 main CI/LIVE and review of the feedback flow. High-risk PRs #523/#578/#551/#514/#515 remain gated.
- **Bounded production evidence (2026-10-30 18:40–20:35 UTC):** Render filtered app ERROR and HTTP 5xx request logs empty; HTTP metrics report 200/204/304/401/404/499 and no 5xx series in this window (not a 24h guarantee). PostgreSQL 18 `era-postgres` available, external allowlist empty; Redis `era-redis-persistent` available with journal_snapshot/noeviction. Legacy free Redis is suspended and is not the active persistent instance. Direct eight-route checks `/health`, `/ready`, `/app/`, protected analytics/PDF/XLSX/media-workspaces/poster-preview on the **new SHA** NOT performed; network DNS blocks direct host access. Real Telegram multi-role and iPhone/Android acceptance not performed. Backup offsite restore still unverified.
- **Acceptance register:** 40 stable requirements, 1 `ПРОВЕРЕНО` = **2.5% strict evidence-based acceptance**, 39 not verified. No new `ПРОВЕРЕНО` claims from CI or merge. A04/B02 remain `В РАЗРАБОТКЕ`; B03 reversible hide/remove from public listing remains `НЕ НАЧАТО`, requires dedicated visibility policy, read-path review and safe additive schema plan (do not misuse cancellation).
- **No real writes:** no real Telegram sends, publications, registrations, points, roles, chats, secrets, destructive migrations, production SQL, mass notifications, or manual deploy. «Траектория открытий» 31 October NOT republished. @MVKSRS_bot separate. No Mafia.
- **Reproduce:** inspect GitHub Actions runs `41124158813`, `41124442221`, `41124442132`; on a repository checkout run `cd frontend && npm run build` and `npx playwright test e2e/event_poster_edit.spec.ts` with disposable E2E backend; `git diff --check`. For production read-only verification after exact LIVE, run `python scripts/production_readonly_smoke.py --expected-sha ece02e943eba890cb7363a18c938b8070b45fa07` from a network-enabled authorized host. Never use production accounts for test writes.
- **Next exact action:** verify #586 main push CI 5/5 and automatic Render exact LIVE; inspect `/health`, `/ready`, `/app/`, 401/403 protected routes, errors/5xx, PG/Redis. Inspect #587 final-head 6/6 and E2E failure logs if needed, fix and re-run. Then risk-review #584/#587 and safely merge only when release gates pass; update this register without clobbering concurrent work. Human blockers: real admin/leader/employee/participant Telegram acceptance, offsite restore, policy for #585 feedback eligibility and #582 media calendar scope, legal signoff. No routine user notification outside 09:00–19:00 Asia/Yerevan.

### 00:48 Asia/Yerevan CI follow-up

- Main push run `41124158813`: 4/5 SUCCESS (frontend, e2e, secret-scan, postgres-migration), Python `test` still IN_PROGRESS; no merge/deploy claimed.
- PR #587 head `40b6a4aa60daf566077e5126d249e483a41d4794`: E2E, frontend, secret-scan and postgres-migration SUCCESS; Python `test` and separate Tests IN_PROGRESS. E2E completed the mocked poster-replacement/no-republish scenario; this is not real Telegram acceptance.
- PR #584 marked ready for review without changing HEAD; source-grounded risk comment `6533081037` records unchanged feedback eligibility issue #585. PR #587 review comment `6533081651` records image-only removal and B03 distinction. Both await the required release gates. Render still last confirmed LIVE `1a8b635792e0b931e079d99dde380bd1a2ffe706`.

### 00:52 Asia/Yerevan latest gate

- PR #587 exact head `40b6a4aa60daf566077e5126d249e483a41d4794`: Bot checks **5/5 SUCCESS** including browser E2E. Separate Tests run `41124442132` remains IN_PROGRESS; do not merge yet. PR #587 remains DRAFT.
- Main push run `41124158813` remains **4/5 SUCCESS**, Python test IN_PROGRESS; automatic Render exact SHA `ece02e943eba890cb7363a18c938b8070b45fa07` not yet confirmed LIVE. Previous LIVE `1a8b635792e0b931e079d99dde380bd1a2ffe706` remains last confirmed. This is an asynchronous CI wait, not a bypassable failure; no manual deploy. No new real Telegram acceptance or changes to the 1/40 verified count.

### 2026-10-31 early morning — release #584, production gate, #587 test follow-up

- **Fresh main:** `b3d631654eaacf529f2ad493e8be60067e53a02a` from exact-head merge of #584 (head `93219e9e6c20565da378a1bf7e82d1e475bc7d76`, 5/5 Bot checks + 1/1 Tests SUCCESS, reviewed bounded attendance/selfie/feedback callbacks/FSM IDs). #584 merged with `expected_head_sha`; no Telegram sends, registrations, points or migrations. Policy issue #585 feedback eligibility remains open and was not changed.
- **Previous main #586 release verified:** `ece02e943eba890cb7363a18c938b8070b45fa07` Bot checks push run `41124158813` 5/5 SUCCESS, automatic Render LIVE deploy `dep-dbig8jlckfvc73c7vqpg` finished 2026-10-30 20:57:09 UTC. Thus A04 is now **ВЫПУЩЕНО**, NOT ПРОВЕРЕНО: no real iPhone/Android Telegram profile acceptance.
- **Current release gate:** new main push Bot checks run `41131875286` started, latest observed 2/5 SUCCESS (frontend, secret-scan), test/e2e/postgres-migration IN_PROGRESS. Render still LIVE previous `ece02e943eba890cb7363a18c938b8070b45fa07`; **#584 merge SHA not yet LIVE**. Do not claim it is deployed or bypass `checksPass`. No manual deploy.
- **#587 independent code/test work:** existing draft PR #587 updated with additional positive-confirmation Playwright coverage of image-only poster removal, confirming no republish and preserved operational event listing; previously only declined-confirmation path was tested. New head `c135c8d1d52a15906ed610a6f9a7bfcf276135ff`, changed `frontend/e2e/event_poster_edit.spec.ts`. New exact-head Bot checks run `41131975182` and Tests run `41131975191` started; older green checks on head `40b6a4a...` do NOT authorize merge. Keep #587 draft until all 6/6 success, risk review, main CI and exact LIVE. B02 remains В РАЗРАБОТКЕ.
- **Source review #587:** authenticated admin event draft/preview/poster upload/remove endpoints in `app/api/v1/admin_event_create.py` all require `require_event_manager`. Upload validates MIME, 5 MiB and image magic bytes. The UI invokes only poster endpoints, not publish/registration/points. Browser test is mocked, NOT real device acceptance. B03 reversible public-list hiding remains NOT STARTED and must not be conflated with image removal.
- **Read-only production evidence:** Render service `autoDeploy=yes`, `autoDeployTrigger=checksPass`; PostgreSQL 18 `era-postgres` available with external IP allowlist empty; persistent `era-redis-persistent` available (journal_snapshot, noeviction); legacy Redis suspended. Filtered Render app ERROR and HTTP 5xx request logs empty in UTC window 2026-10-30 20:45–22:00 (bounded, not perpetual guarantee). Direct HTTP `/health`, `/ready`, `/app/`, protected analytics/PDF/XLSX/media-workspaces/poster-preview on new SHA **not checked**: container DNS failed resolving production host. Do not substitute CI or logs for direct route acceptance. Offsite backup restore and real multi-role Telegram/Mini App acceptance remain unconfirmed.
- **Acceptance:** 1/40 ПРОВЕРЕНО = **2.5% strict acceptance**; 39 remain. A04 now ВЫПУЩЕНО but not ПРОВЕРЕНО; no other acceptance status changed. Legal/organizational policy (#585 feedback, #582 cross-area media calendar), owner review, external backup restore, leader panel and real mobile role tests remain blocked on authorized human actions.
- **No prohibited writes:** no event announcements, no «Траектория открытий» publication, no Mafia, no real Telegram changes, user data/points/roles/secrets edits, destructive migrations or manual deploy. @MVKSRS_bot separate.
- **Reproduce/next:** GitHub Actions runs `41131875286`, `41131975182`, `41131975191`; `BOT_TOKEN=0000000000:CITESTTOKEN python -m pytest -q tests/test_supplemental_event_callback_state_guards.py`; `cd frontend && npx playwright test e2e/event_poster_edit.spec.ts`; `git diff --check`. First wait for exact current main 5/5 and Render LIVE `b3d631654eaacf529f2ad493e8be60067e53a02a`, then run read-only production smoke on network-enabled authorized host. Next, after #587 exact-head 6/6 and review, merge with expected_head_sha and verify new main/Render exact SHA. If CI fails, inspect job logs, fix on PR branch and rerun; do not merge on stale green. Continue independent B03 read-path/policy analysis without changing real data. Do not overwrite concurrent checkpoint branches.

- **B03 source-grounded next implementation design (not shipped):** `app/services/event_service.py::published_events` currently filters only status and future date. `app/database/event_experience.py::EventExperience` is the one-to-one companion suitable for an additive `show_in_public_listing` default-true flag, with legacy rows treated as visible. Build admin-only reversible hide/show endpoint with audit and no notifications, and filter *only* general discovery listings (also inspect bot listing callers); preserve direct `GET /events/{id}`, participant registration/history, ICS, QR, points and existing poster bytes. Do not conflate B03 with #587 image-only deletion or cancellation. Before merge: migration forward/backward safety, old-row compatibility, public-list and registered-participant tests, scoped 401/403 and no accidental publish, exact-head CI and human approval for direct-link behavior. No B03 code or schema change made in this run.

### 2026-10-31 02:36+ Asia/Yerevan — poster editor release, new B03 implementation

- **Fresh main** `ed5a6f5672f039c64392129434cc324541d92268` (merge PR #587, exact head `c135c8d1d52a15906ed610a6f9a7bfcf276135ff`, review 5719413683). PR #587 Bot checks run `41131975182` **5/5 SUCCESS** and separate Tests `41131975191` **1/1 SUCCESS**. Merged with `expected_head_sha` after review; no manual deploy.
- **Main CI gate:** push Bot checks `41139294980` at last read **3/5 SUCCESS** (frontend, postgres-migration, secret-scan); Python test and E2E IN_PROGRESS. Do not claim main CI complete. **Render LIVE remains previous main** `b3d631654eaacf529f2ad493e8be60067e53a02a` (deploy `dep-dbih4pei0phs739e2q9g`, finished 2026-10-30 21:57:17 UTC). The previous SHA's main push CI `41131875286` was 5/5 SUCCESS. New `ed5a6...` not yet confirmed LIVE; `autoDeployTrigger=checksPass`, no manual deploy.
- **B02:** published-event poster editor is merged to main but not yet confirmed LIVE; keep **В РАЗРАБОТКЕ** until exact LIVE. Real admin iPhone/Android acceptance remains unconfirmed after deployment. Image-only removal is not B03 event-list hiding.
- **New B03 implementation DRAFT PR #589** `feat/event-public-listing-visibility-20261031`, current exact HEAD `96701cb18b6b994c954552e7d1a3e95fb838df03`. New manager-only PATCH `/admin/events/{id}/listing`, reversible `show_in_public_listing` default-true flag, audit old/new values, no Telegram sends, no publish, no data deletion; filters public event discovery in `event_service.published_events` and `activity_service.list_events(all/for_me)`. Personal `mine`/history, direct event link, QR/ICS, registrations and points deliberately untouched. Admin operational list and Mini App hide/restore controls with confirmation added. Legacy events lacking EventExperience remain visible. Additive migration `0065_event_public_listing` is **not deployed**. Isolated SQLite test and mocked Playwright E2E added, not real acceptance.
- **Changed files #589:** `app/database/event_experience.py`, `app/services/event_service.py`, `app/services/activity_service.py`, `app/api/v1/admin_event_create.py`, `app/api/v1/admin.py`, `frontend/src/api/adminEvents.ts`, `frontend/src/types/admin.ts`, `frontend/src/screens/admin/events/EventsList.tsx`, `alembic/versions/0065_event_public_listing.py`, `tests/test_event_public_listing_visibility.py`, `frontend/e2e/event_public_listing.spec.ts`.
- **#589 CI:** exact-head Bot checks run `41139599441`, Tests `41139599458` queued/pending at last read; older head `6223ade...` checks are stale. DRAFT and HIGH RISK; review 5719436745 requires all six checks, isolated PG upgrade, owner decision on direct-link visibility and real manager/participant acceptance before any merge. If CI fails, inspect exact job logs and fix on this same PR branch; do not duplicate PR.
- **Production checks:** Render filtered app ERROR and request 5xx logs **empty** for 2026-10-30 21:30–23:00 UTC; this is bounded only. Direct `/health`, `/ready`, `/app/` and protected analytics/PDF/XLSX/media-workspaces/poster-preview **not directly checked** on new SHA (container DNS and web URL access failed). No new PG/Redis health evidence in this interval beyond previous checkpoint; do not infer latest backup/offsite restore.
- **Acceptance register:** still **1/40 ПРОВЕРЕНО = 2.5%**, 39 not accepted. B03 changed from НЕ НАЧАТО to В РАЗРАБОТКЕ, B02 not yet verified. CI/merge != human acceptance.
- **Safety:** no real Telegram sends, no prohibited 31 Oct «Траектория открытий» publication, no Mafia, no production participants/events, no points/registration/roles/chats/secrets changes, no destructive migrations or manual Render deploy. @MVKSRS_bot remains separate. PR #589 migration exists in a branch only.
- **Reproduce:** GitHub Actions runs `41139294980`, `41139599441`, `41139599458`. Local disposable checkout: `BOT_TOKEN=0000000000:CITESTTOKEN python -m pytest -q tests/test_event_public_listing_visibility.py`; `cd frontend && npx playwright test e2e/event_public_listing.spec.ts e2e/event_poster_edit.spec.ts`; `alembic upgrade head` **only against disposable PG test database**; `git diff --check`. On network-enabled authorized host after LIVE, `python scripts/production_readonly_smoke.py --expected-sha ed5a6f5672f039c64392129434cc324541d92268`. Never run migration or test writes against production manually.
- **Next exact action:** complete main `41139294980` 5/5, observe automatic Render LIVE exact `ed5a6...`, verify read-only HTTP/PG/Redis/logs. Then complete #589 exact-head CI, fix failures if any, run disposable PostgreSQL migration/visibility proof, review owner policy on hidden direct links; leave high-risk draft until approval. Continue independent low-risk tasks. Human blockers: actual admin/leader/staff/participant Telegram acceptance, direct-link privacy policy, offsite backup restore, feedback eligibility #585, media scope #582, legal signoff.
- **Daily summary delivery date:** none (outside 09:00–19:00 Asia/Yerevan); do not send routine notification overnight.

### 02:xx Asia/Yerevan — read-only infrastructure and CI follow-up

- Fresh Render resource inventory: `era-postgres` PostgreSQL 18 (`dpg-d91r19vavr4c73fs837g-a`) **available**, external allowlist empty; `era-redis-persistent` Redis 8.1.10 (`red-db4n2cnlk1mc73d7rei0`) **available**. Legacy free Redis suspended. This proves resource status, not application query success or backup restore.
- Latest observed exact main `ed5a6f5672f039c64392129434cc324541d92268`; main push run `41139294980` **4/5 SUCCESS** (frontend, e2e, postgres-migration, secret-scan), Python test IN_PROGRESS. Render LIVE remains `b3d631654eaacf529f2ad493e8be60067e53a02a`, so B02 still not production-verified. No manual deploy.
- PR #589 final head `96701cb18b6b994c954552e7d1a3e95fb838df03`: Bot checks `41139599441` secret-scan/frontend SUCCESS, e2e/test/postgres-migration IN_PROGRESS; separate Tests `41139599458` IN_PROGRESS. Risk review 5719436745 posted; high-risk DRAFT not merged.
- Direct production HTTP probes by both runtime and public web reader failed to access host; **no 200/401/403 claimed**. Latest bounded request-5xx and app-error log searches were empty. Continue only read-only verification; no production test writes.


### 2026-10-31 03:xx Asia/Yerevan — #589 CI repair and exact production verification

- **Fresh main:** `ed5a6f5672f039c64392129434cc324541d92268`, push Bot checks run `41139294980` **5/5 SUCCESS** (postgres-migration, frontend, e2e, test, secret-scan). Render service `srv-d91r1j7avr4c73fs8h00` autoDeploy=yes, checksPass; exact **LIVE SHA matches main**, deploy `dep-dbihv9mi0phs739f35vg` finished 2026-10-30 22:53:34 UTC. No manual deploy. PR #587 published-poster editor is therefore **ВЫПУЩЕНО**, but not ПРОВЕРЕНО (no real administrator/mobile Telegram acceptance). A04 remains ВЫПУЩЕНО, not accepted.
- **#589 failure reproduced from CI evidence:** old head `96701cb18b6b994c954552e7d1a3e95fb838df03` Bot checks and separate Tests each failed the same existing test `tests/test_admin_operations_api.py::EventOperationsApiTests::test_operational_list`: test's fake `SimpleNamespace` session lacked async `get` used by the new operational listing visibility read; all other 2394 tests passed, 1 skipped. This was a **test-double regression**, not a proven production failure. Source: jobs `124350666333` and `124350663367`.
- **Code/test change on existing #589 branch, not a duplicate PR:** updated `tests/test_admin_operations_api.py` to use `SimpleNamespace(get=AsyncMock(return_value=None))` and assert legacy default visibility true; added a separate hidden-event operational-list test asserting false visibility and unchanged registration counts. Commits `f88b70b3ee655f3f184e5c5cef1530bd95abf7dc`, then **current exact PR HEAD `3aa32cb5f8583bc2bcfc3d257115f2fea3b60db2`**. New required 5/5 Bot checks + 1/1 Tests must run and pass on this HEAD; checks were not yet visible immediately after push. Do not reuse old green runs. Targeted test execution is pending GitHub CI because this runtime cannot clone GitHub (DNS resolution unavailable); do not label local tests passed.
- **#589 remains HIGH-RISK DRAFT, NOT MERGED:** additive migration `0065_event_public_listing` (default-true) passed PostgreSQL migration CI on prior HEAD, but owner must decide whether hidden events remain accessible by direct link and authorize rollout after migration/privacy review; real manager/participant acceptance remains unavailable. No destructive migrations, Telegram messages, registrations, points or real events modified. Separate @MVKSRS_bot untouched. Keep PR draft and avoid release even if CI turns green without policy decision.
- **Read-only Render:** app error-level logs and request HTTP 5xx logs returned empty for bounded 2026-10-30 22:30–23:40 UTC. Render HTTP metrics in 22:50–23:35 UTC include 200/401/404, no 5xx status series; **aggregated counts cannot prove the exact eight routes**. No per-route request logs were returned. Direct `/health`, `/ready`, `/app/` and protected analytics/PDF/XLSX/media-workspaces/poster-preview remain **not directly verified** from this runtime: public web reader cannot access host, container cannot resolve DNS. PG/Redis current query health and offsite backup restore not newly checked; previous bounded infrastructure evidence remains dated.
- **Acceptance:** 1/40 ПРОВЕРЕНО = **2.5%**; 39 open. B02 now ВЫПУЩЕНО but not accepted. B03 В РАЗРАБОТКЕ. No new real Telegram/Mini App acceptance. No routine overnight notification; last daily summary date unchanged.
- **Reproduce:** `BOT_TOKEN=0000000000:CITESTTOKEN python -m pytest -q tests/test_admin_operations_api.py tests/test_event_public_listing_visibility.py`; `cd frontend && npx playwright test e2e/event_public_listing.spec.ts`; `alembic upgrade head` only against disposable PG test database; `python scripts/production_readonly_smoke.py --expected-sha ed5a6f5672f039c64392129434cc324541d92268` from an authorized network-enabled host. Review `https://github.com/davidbagh22/era-telegram-bot/pull/589` and exact-head CI.
- **Next concrete action:** await current #589 HEAD checks and inspect failures; if green, conduct security/privacy and migration review but leave high-risk PR unmerged pending direct-link owner decision and real multi-role acceptance. Continue independent safe work (e.g. low-risk regression tests on existing drafts). Confirm production route auth and backups only with actual evidence; never fabricate results or trigger manual deploy. Do not publish «Траектория открытий» or other unapproved ERA announcements, do not add Mafia.

- **Independent #468 review:** opt-in 3-hour media deadline reminder draft exact HEAD `8d2cf57ee60d0c745f3a6115a3c691cecd63fe84` has 6/6 green CI and defaults `media_deadline_3h_enabled=False`. Source review confirms disabled behavior keeps existing 24h stage. However fresh GitHub mergeability after ready-for-review recalculation is **DIRTY / mergeable=false** against current main (earlier clean result was stale). Returned #468 to **DRAFT**, documented conflict in PR comment `6535851647`; **NO merge, NO deploy, NO 3h sends**. Next independent action: reconcile conflict with current main, rerun exact-head 6/6, review again, keep flag disabled until explicit delivery approval.

- **Final CI observation this run:** #589 exact HEAD `3aa32cb5f8583bc2bcfc3d257115f2fea3b60db2` Bot checks run `41145753455` and separate Tests `41145753216` IN_PROGRESS; frontend and secret-scan SUCCESS, e2e, postgres-migration, both Python test jobs still IN_PROGRESS. Thus **2/6 SUCCESS, 4 pending**; no merge. Production main/LIVE remains `ed5a6f5672f039c64392129434cc324541d92268` as above. Next run must fetch fresh checks and main/LIVE rather than assume completion.


### 2026-10-31 04:xx Asia/Yerevan — exact release, #589 CI, independent poster backend regression

- **Fresh main and production:** main `ed5a6f5672f039c64392129434cc324541d92268`; push Bot checks run `41139294980` **5/5 SUCCESS**. Render latest unique LIVE deploy `dep-dbihv9mi0phs739f35vg`, exact same SHA, finished 2026-10-30 22:53:34 UTC; service `autoDeploy=yes`, `autoDeployTrigger=checksPass`. No manual deploy. B02 is **ВЫПУЩЕНО** (published-poster editor), not ПРОВЕРЕНО: real Telegram administrator/iPhone/Android acceptance unavailable. A04 remains ВЫПУЩЕНО.
- **#589 exact-head CI:** DRAFT `feat/event-public-listing-visibility-20261031`, head `3aa32cb5f8583bc2bcfc3d257115f2fea3b60db2`; Bot checks `41145753455` **5/5 SUCCESS** and Tests `41145753216` **1/1 SUCCESS** on that HEAD. Additive PostgreSQL migration and regression suite green in CI. **DO NOT MERGE:** requires owner policy on hidden direct-link accessibility and real admin/participant acceptance; high-risk visibility semantics and schema rollout. Existing PR retained, no duplicate.
- **Independent low-risk test-only change:** new DRAFT PR #590 `test/published-poster-backend-invariants-20261031`, head `9c307e2221c1473d311371ed2086099b0ef2e21f`; new file `tests/test_published_poster_backend_invariants.py`. Disposable SQLite regressions verify image-only replacement/removal and private no-store preview, invalid MIME/signature/oversize refusal, unchanged published event/registration/points/announcement receipt, and no changed-event notification. No feature behavior or production writes. Initial exact-head runs: Bot checks `41151266656` and Tests `41151266523` **IN_PROGRESS**, secret-scan success; never merge until all six succeed, review and expected_head_sha. Local tests unavailable because runtime lacks aiogram and GitHub DNS; CI evidence only.
- **Read-only Render 2026-10-30 23:30–2026-10-31 00:45 UTC bounded:** app error-level and request 5xx log filters empty; status-code metrics in 23:30–00:30 UTC show 200/401/404, no 5xx series. This does **not** prove exact eight route responses. Direct `/health`, `/ready`, `/app/`, protected analytics/PDF/XLSX/media-workspaces/poster-preview on exact LIVE SHA remain **not directly confirmed** from this runtime due to DNS/network; PG/Redis query success and external offsite restore not newly confirmed.
- **Acceptance:** stable 40 requirements, **1/40 ПРОВЕРЕНО = 2.5%**; 39 unaccepted. B02 updated to ВЫПУЩЕНО, B03 В РАЗРАБОТКЕ. No real administrator/leader/staff/participant acceptance. No unauthorized Telegram sends, no prohibited 31 Oct «Траектория открытий» publication, no Mafia, no real user data/points/roles/chats/secrets modifications, no destructive migration, no manual deploy. @MVKSRS_bot separate.
- **Reproduce:** GitHub Actions `41145753455`, `41145753216`, `41151266656`, `41151266523`; `BOT_TOKEN=0000000000:CITESTTOKEN python -m pytest -q tests/test_published_poster_backend_invariants.py tests/test_event_public_listing_visibility.py` (second file only on #589 branch); `git diff --check`; read-only `python scripts/production_readonly_smoke.py --expected-sha ed5a6f5672f039c64392129434cc324541d92268` from an authorized network-enabled host. Never run test writes against production.
- **Next exact action:** inspect #590 exact-head six CI checks, fix any failures on same branch; after green and risk review, mark ready and merge with `expected_head_sha`, verify main CI 5/5 and automatic Render LIVE exact SHA, inspect logs and routes. Continue independent tasks. #589 remains high-risk DRAFT pending owner direct-link privacy policy and real role acceptance. Human blockers: authorized multi-role Telegram acceptance, offsite restore, #585 feedback eligibility, #582 media scope, legal approval. Daily summary delivery date unchanged (none); no ordinary overnight notification.

- **04:xx final follow-up:** #590 exact-head CI still IN_PROGRESS: Bot checks `41151266656` frontend, postgres-migration, secret-scan SUCCESS; test/e2e running. Separate Tests `41151266523` running. Review comment `5720159893` recorded source-only risk analysis; no merge or release yet. #589 exact-head 6/6 remains green but DRAFT for owner privacy decision; PR comment `6536650833` documents gate. Fresh Render inventory: PostgreSQL 18 `era-postgres` available with external allowlist empty; persistent Redis 8.1.10 `era-redis-persistent` available (journal_snapshot/noeviction), legacy free Redis suspended. No SQL test writes or external DB opening. Direct production HTTP route acceptance still not evidenced. Next run: check #590 test/e2e outcome and logs, fix if needed; do not merge before all 6/6 exact-head checks.

### 2026-10-31 05:35+ Asia/Yerevan — exact #590 merge, independent B03 idempotence regression

- **Continuation:** read this checkpoint branch, main register (40 requirements), open PRs/issues, exact-head CI and Render; no audit restart. Latest observed GitHub `main` from branch API: `c8224aa93e5133c9de965c42049c9620facca249` (PR #590 merge). The previous main `ed5a6f5672f039c64392129434cc324541d92268` had push CI `41139294980` 5/5 SUCCESS and automatic Render LIVE `dep-dbihv9mi0phs739f35vg` at 2026-10-30 22:53:34 UTC.
- **Low-risk release:** test-only PR #590 exact HEAD `9c307e2221c1473d311371ed2086099b0ef2e21f` passed Bot checks run `41151266656` **5/5 SUCCESS** (test, e2e, frontend, postgres-migration, secret-scan) and separate Tests `41151266523` **1/1 SUCCESS**. Source-only risk review was already recorded on PR; marked ready and merged with `expected_head_sha`. Merge commit `c8224aa93e5133c9de965c42049c9620facca249`. Changed file `tests/test_published_poster_backend_invariants.py` only: disposable SQLite poster replacement/removal, MIME/signature/size rejection, private preview, unchanged registration/event points/announcement state, no notification. No production behavior changes.
- **New main release gate:** push Bot checks run `41156133641` on exact merge SHA; latest observed **2/5 SUCCESS** (frontend, secret-scan), Python test, e2e and postgres-migration IN_PROGRESS. Render latest LIVE **still** `ed5a6f5672f039c64392129434cc324541d92268` (previous deploy); do not claim new SHA deployed until exact Render LIVE. Service `autoDeploy=yes`, `autoDeployTrigger=checksPass`; **no manual deploy**.
- **Independent B03 work, existing HIGH-RISK DRAFT #589 (not merged):** updated `tests/test_event_public_listing_visibility.py` on `feat/event-public-listing-visibility-20261031` to prove duplicate hide requests are idempotent: one audit entry, event remains published, registration retained; restore still audited. New exact PR HEAD `3a1332b55ca11e609b183acc4200fba01334a6df`; Bot checks `41156180326` and separate Tests `41156180486` IN_PROGRESS. Previous green 6/6 was on OLD head `3aa32cb...` and is now stale. Requires new exact-head 6/6 and source review; **do not merge** without owner decision on direct-link privacy, isolated PG migration/rollback policy and real manager/participant acceptance. Additive migration 0065 remains branch-only.
- **Read-only infrastructure:** Render PostgreSQL 18 `era-postgres` status available, external IP allowlist empty; persistent Redis 8.1.10 `era-redis-persistent` status available (journal_snapshot/noeviction). This is resource status, not application query proof. In bounded UTC interval 2026-10-31 00:40–01:38, filtered application ERROR and HTTP 5xx request logs returned empty; HTTP metrics show 200/304/401, no 5xx status series. Direct route acceptance on new SHA remains **UNVERIFIED**: runtime DNS fails resolving production hostname, public web reader cannot access /health, /ready or /app/. Aggregated HTTP metrics cannot prove eight individual paths. Backup offsite restore, real Telegram roles/iPhone/Android and PG application queries not newly checked.
- **Register unchanged:** **1/40 ПРОВЕРЕНО = 2.5% strict acceptance**; 39 remain unaccepted. A04 and B02 ВЫПУЩЕНО but lack real device/admin acceptance; B03 В РАЗРАБОТКЕ. No fabricated multi-role acceptance or real production event list.
- **Safety:** no Telegram sends, no «Траектория открытий» publication, no Mafia, no real participants/events/registrations/points/roles/chats/secrets edits, no destructive migrations, no production SQL and no manual Render deploy. @MVKSRS_bot untouched. No ordinary user notification outside 09:00–19:00 Asia/Yerevan; daily summary date still none.
- **Reproduce:** GitHub Actions runs `41151266656`, `41151266523`, `41156133641`, `41156180326`, `41156180486`; on disposable checkout `BOT_TOKEN=0000000000:CITESTTOKEN python -m pytest -q tests/test_published_poster_backend_invariants.py` (main) and `BOT_TOKEN=0000000000:CITESTTOKEN python -m pytest -q tests/test_event_public_listing_visibility.py` (#589 branch); `git diff --check`. On network-enabled authorized host only, `python scripts/production_readonly_smoke.py --expected-sha c8224aa93e5133c9de965c42049c9620facca249`. Never run test writes against production.
- **Next exact action:** wait for main push run `41156133641` 5/5, observe automatic Render exact LIVE `c8224aa...`, then run eight-route read-only smoke from a network-enabled authorized host and check bounded errors/5xx, PG/Redis. Inspect new #589 6/6 and failures; keep HIGH-RISK DRAFT until direct-link privacy/rollback owner decision and real role acceptance. Continue independent safe regressions; do not overwrite other checkpoint branches. Human blockers: multi-role Telegram acceptance, external backup restore, feedback eligibility #585, cross-area calendar #582, legal signoff.

### 2026-10-31 05:xx Asia/Yerevan — independent poster authorization regression #591

- **New independent test-only DRAFT PR #591** `test/poster-admin-auth-boundaries-20261031`, exact HEAD `32d19cd740d8729c7fef63d098cad94be3794c9c`, based on main merge `c8224aa93e5133c9de965c42049c9620facca249`. New file `tests/test_published_poster_authorization.py` uses isolated FastAPI TestClient to assert **401 anonymous**, **403 ordinary participant**, and **403 department-scoped-only events.manage** for four routes: admin poster preview, upload, remove and draft read. Unauthorized requests must never query the DB. No runtime logic, production data, messages, roles or secrets changed. Source-only review `5720395118` records scope and limits. Exact HEAD Bot checks `41156286011` and Tests `41156286014` IN_PROGRESS (frontend/secret-scan already SUCCESS; remaining checks pending). Do not merge before all 6/6 and review.
- **Current gates at last read:** main `c8224aa93e5133c9de965c42049c9620facca249` push CI `41156133641`: frontend, secret-scan, postgres-migration **3/5 SUCCESS**; Python test and E2E IN_PROGRESS. Render last LIVE `ed5a6f5672f039c64392129434cc324541d92268`, exact new main SHA not yet deployed. #589 head `3a1332b55ca11e609b183acc4200fba01334a6df`: Bot checks `41156180326` frontend/secret-scan SUCCESS, other checks and separate Tests `41156180486` IN_PROGRESS. #589 stays HIGH-RISK DRAFT pending human direct-link privacy decision, migration/rollback review and real role acceptance.
- **No route acceptance:** direct runtime DNS failed for production host; public reader cannot access /health, /ready, /app/. Render aggregated 200/304/401 cannot prove per-route status or JSON payload. No manual deploy. Next: finish exact-head CI, fix failures on existing branches, safely merge #591 only if all six green; verify main push CI and automatic exact Render LIVE; keep #589 draft. No change to 1/40 (2.5%) accepted. Daily summary date remains none; no overnight user notification.
