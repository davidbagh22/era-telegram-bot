# ЭРА — автономная разработка

Updated: 2026-10-30 UTC. This is the primary continuation point for the hourly task
`6adcbd42ede08191a5c0a946e4147b52` («ЭРА — разработка до полной готовности»).
Read this first, then current main/PR/CI/Render; consult older AI_TASK_STATE.md and
checkpoint documents only for evidence relevant to the selected task. Do not restart
the audit or create another automation. Existing task updated with the user's full
30 October autonomous-development requirements, hourly, Asia/Yerevan.

## Release and current change

- Last observed main AND Render LIVE: `1a8b635792e0b931e079d99dde380bd1a2ffe706`.
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
| A04 | Remove «Мой путь» from profile | В РАЗРАБОТКЕ | Current branch; CI, release and real profile acceptance |
| A05 | Buttons, typography and logo | В РАЗРАБОТКЕ | Mobile visual review against agreed design |
| A06 | iPhone and Android Mini App | В РАЗРАБОТКЕ | #620 iOS ICS calendar import, real Telegram iPhone/Android clients, not only Playwright |
| B01 | Event create/publish/edit | ВЫПУЩЕНО | #620 calendar export UX; real authorized scenario, no test announcement |
| B02 | Edit published event poster | В РАЗРАБОТКЕ | Wizard supports poster changes; published entry flow unconfirmed |
| B03 | Hide/remove events from general poster listing | НЕ НАЧАТО | Reversible visibility, retain history/registrations |
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


## Continuation checkpoint — 2026-11-01 16:49 UTC (read-only evidence)

- Render API reports automatic deployment `dep-dbjmqceq1p3s73au65h0` status `live`, commit `f766e572a085edefa8fc025bf15e4fd8b0c1888b` (PR #614). No manual deploy.
- PR #614 is closed/merged according to recent GitHub issue listing; PRs #613/#612 likewise closed. These are release facts, **not** multi-role acceptance.
- The earlier register remains **1/40 verified (2.5%)**, pending a full evidence-backed register reconciliation; do not mark B05/E11 verified solely from the URL hardening release.
- GitHub combined commit-status endpoint returned an empty status list for the above SHA; this is **not** proof of failed or passed GitHub Actions checks. Recheck exact push workflows separately.
- Existing unresolved concerns to inspect before any merge: #589 (privacy), #605 (timezones), event listing privacy/history drafts #484/#486, plus current open PRs and changed HEAD CI. Do not duplicate existing work.
- Next safe action: fetch latest GitHub main, enumerate current PRs/issues and exact HEAD six required CI results; select an independent low-risk patch. Complete review and guarded merge only on 6/6 SUCCESS, then main CI and automatic Render checksPass, and actual read-only production smoke. Do not create test production participants/events or send Telegram messages.
- Human blockers unchanged: distinct authenticated Telegram roles, actual iOS/Android acceptance, scoped production event list and isolated restore evidence. Mark those `Не подтверждено` until verified.
- Daily summary date: no new daily summary recorded by this checkpoint; do not assume a chat reply constitutes the scheduled summary.

- Additional Render production evidence, 2026-11-01 16:57 UTC: deploy event `deploy_ended` reports `succeeded` for `dep-dbjmqceq1p3s73au65h0`; trigger is `newCommit` and `manual=false`. HTTP metrics after deploy show 25 responses 200, 4 responses 204 and 1 response 404 in sampled 16:54 bucket; instance count 1. Filtered 5xx request logs 16:49–16:57 UTC returned no entries. These limited metrics do not prove all endpoints or role flows healthy. Direct `/health` and `/ready` via public web fetch unavailable; acceptance remains unconfirmed.


## Continuation checkpoint — 2026-11-01 17:4x UTC (pending CI)

- PR #615 merged with exact HEAD `0a0d10e076f6eebd4a8cd3e57b9b99ec45dfd0bf` after 6/6 SUCCESS and zero review threads. Main merge SHA `faf58c6a4073281da5e4eab021014e40d65ce16f`; main push CI run `41332598478` was still in progress at observation. **Do not claim this SHA LIVE until automatic Render checksPass.** Previous confirmed Render LIVE was `f766e572a085edefa8fc025bf15e4fd8b0c1888b`.
- Source inspection discovered event wizard's `datetime-local` task deadline was stored without timezone (`AdminEventCreatePanel.tsx`), while `EventActivity.deadline` is timezone-aware. This makes the existing PR #605 assumption that *all* naive deadlines are UTC unsafe for newly entered editor-local times. Keep #605 DRAFT pending a separate legacy timestamp policy review; do not blindly merge it.
- Current functional change in PR #617 (this branch): convert newly edited task deadlines to explicit UTC ISO instants; display aware stored values in the editor's local timezone; leave legacy naive strings untouched until edited. Browser-only E2E uses `Asia/Yerevan`, checks 18:00 local -> 14:00Z and reload round-trip. No production participant/event or Telegram publication created by this code change. CI and real Telegram acceptance pending.
- B05/B07 remain `В РАЗРАБОТКЕ`; strict acceptance stays **1/40 = 2.5%**. This frontend change does not repair the existing scheduler `created_by` constructor error (#575) or duplicate-activity risk (#581), nor does it establish backend #605 safety.
- Next: verify exact HEAD PR #617 5/5 Bot checks + 1/1 Tests, source review, guarded merge with `expected_head_sha` only if green; then main push CI and automatic Render checksPass exact SHA, read-only production checks. Afterward review #523/#575/#581 concurrency on isolated PostgreSQL and #589 public-listing privacy. Real admin/leader/employee/participant acceptance is **Не подтверждено**.
- No manual deploy, real data mutations, points, event publications, uncertain delivery replays, security setting changes or secrets.


## Continuation checkpoint — 2026-11-01 ~18:36 UTC (release + mobile task)

- PR #617 exact HEAD `8e179d28ea0bea8bf32d708faaee8fb39b9f8982` completed **6/6 SUCCESS**: Bot checks secret-scan, test, frontend, e2e, postgres-migration and separate Tests test. No unresolved review threads. Source inspected, then marked ready and merged with `expected_head_sha`; new main merge SHA `3ace34c116924a0f005dead65eed03379b578fdb`.
- Predecessor main `faf58c6a4073281da5e4eab021014e40d65ce16f` automatically became Render LIVE through `dep-dbjnt1bm8hqs7380o100` (18:03:50 UTC, no manual deploy). **New main `3ace34...` not yet confirmed Render LIVE** at first post-merge check; main push CI is not exposed by the PR-only GitHub workflow connector. Recheck both; never equate an absent commit-status list with passed CI.
- Current branch `fix/event-wizard-task-mobile-20261101`: A05/A06/B05 independent frontend-only improvement for 320px Telegram view. Task deadline + points fields switch from fixed `1fr 100px` grid to responsive `auto-fit` minmax, with width-constrained inputs. Existing isolated Playwright Asia/Yerevan round-trip test additionally checks date and points field bounding boxes at 320px; CI is the test gate. No API, DB, real events, Telegram sends, points, migration, secrets, settings or manual deploy.
- Do not merge this branch without exact HEAD 5/5 Bot checks + 1/1 Tests, review, guarded merge, main CI, automatic Render checksPass exact SHA, read-only production checks. No real iPhone/Android acceptance; mark `Не подтверждено`.
- Strict register unchanged: **1/40 = 2.5%** verified. Existing drafts #589 (listing privacy) and #605 (legacy deadline semantics) remain blocked for policy review; #575/#581 wizard sync issues remain open and require disposable PostgreSQL proof before production change.
- Next: check main `3ace34...` automatic Render LIVE and main push CI; then exact-head CI for this mobile PR and review; merge only if all 6 SUCCESS and no conflicts. Recheck automatic Render after merge. No unauthorized announcement, no Mafia, no uncertain delivery replay.


## Continuation checkpoint — 2026-11-01 19:35 UTC (PR #618 release, next mobile fix)

- PR #618 HEAD `3b73131ee21fdb874cb9c4f4f76f88d9e96ddb6e` completed **6/6 SUCCESS** on exact HEAD (Bot checks: secret-scan, test, frontend, e2e, postgres-migration; separate Tests: test). Source patch inspected and no unresolved review threads. Marked ready and merged with `expected_head_sha`; new main merge SHA **`f4e4c99f392b2ef3a57ed24bd2282f1c34027172`**.
- Predecessor main `3ace34c116924a0f005dead65eed03379b578fdb` became automatic Render LIVE at 2026-11-01 18:55:34 UTC, deploy `dep-dbjoln3ncjis73dr76k0`. Do **not** claim new main `f4e4c99...` LIVE until Render checksPass exact SHA. New main push Bot checks run `41342415712` was in progress, with frontend/secret-scan SUCCESS and e2e/test/postgres-migration pending at 19:35 UTC.
- Next independent task on branch `fix/event-wizard-program-mobile-reminders-20261101`: A05/A06/B01 mobile program editor previously fixed its grid at `100px 1fr` and could clip native time input or presenter on 320px Telegram; use responsive grid and constrained input widths. Also avoid mutating React draft state by replacing in-render `draft.reminders.sort(...)` with `[...draft.reminders].sort(...)`. Add isolated Playwright 320px program-field test. No production events, points, registration, messages, DB, migrations or secrets touched.
- **Next:** create/review PR for this branch, wait for exact HEAD 6/6 CI, review, merge only with `expected_head_sha` if no conflict and previous main CI gate satisfied; then check new main push 5/5, automatic Render exact LIVE and read-only production checks. If pending, leave PR draft and checkpoint. No manual deploy.
- Existing #589 public listing privacy, #605 legacy timezone policy, #575/#581 task synchronization remain open and high-risk; no duplicate PR. Newly filed #616 expert platform is a separate P1 backlog; before implementation explicitly extend acceptance register and denominator.
- Strict acceptance remains **1/40 = 2.5%**. Real admin, manager, employee and participant acceptance, real iOS/Android, authenticated event list and scoped Telegram actions: **Не подтверждено**. Do not publish prohibited event, other unauthorized posts, or replay uncertain delivery.
- Daily summary for 2026-11-01: earlier user-facing release summaries exist; do not send another ordinary summary outside 09–19 Asia/Yerevan. This checkpoint is not evidence of real multi-role acceptance.


## Continuation checkpoint — 2026-11-01 20:4x UTC (PR #619 release and P0 calendar bug #620)

- Reviewed PR #619 exact HEAD `273c388441dd35fb2b94097539287c3aefdb2b19`: **6/6 SUCCESS** (Bot checks run 41342542935: secret-scan, test, frontend, e2e, postgres-migration; Tests run 41342542955: test); no unresolved review threads. Predecessor main `f4e4c99f392b2ef3a57ed24bd2282f1c34027172` push CI run 41342415712 finished 5/5 SUCCESS and Render automatically became LIVE at 19:50:19 UTC, deploy `dep-dbjpfbivcj2c73f912v0`. PR #619 marked ready and merged with guarded `expected_head_sha`; new main SHA **`bf899dbda3a219f8759925ff4df7ad8a1955b238`**.
- New main push CI run **41347627625** was still in progress (frontend, secret-scan, postgres-migration SUCCESS; e2e and test pending). **New main not yet confirmed LIVE**. Do not infer main CI from PR checks; recheck exact push run and automatic Render checksPass.
- **P0 issue #620** filed 2026-11-01 20:26 UTC: real iPhone Telegram user saw raw `BEGIN:VCALENDAR` and garbled Cyrillic on tapping calendar. Existing backend `build_event_calendar` already encodes UTF-8 and folds lines by 75 octets; API already responds `text/calendar; charset=utf-8` with attachment header. The actual frontend was fetching authenticated ICS as a Blob and invoking `a.download`, which iOS Telegram WebView may preview as raw text. Do not change production event #22 or any event data.
- Independent branch `fix/ios-calendar-share-google-fallback-20261102` from main `bf899...`: calendar UI now offers explicit Google Calendar template (Asia/Yerevan local time converted to UTC, Unicode title/description/location) and Apple .ics file share via supported Web Share API; **never** uses blob URL fallback on iOS when native file sharing is unavailable, instead shows an actionable Google/Safari explanation. Non-iOS retains .ics download. Added `X-Content-Type-Options: nosniff` to ICS response; Python UTF-8/CRLF/75-octet/headers regression and isolated Playwright Google/iOS-share/fallback tests. No database migrations, event publications, participants, balances, Telegram sends, secrets, or manual deploy.
- **Acceptance blocker:** a real iPhone Telegram WebView + Apple Calendar share-sheet must be checked by a human; browser E2E alone cannot establish native import. In clients where navigator.share({files}) is unsupported, Apple native import is not claimed functional; Google Calendar fallback is available. No unsupported server token sharing, public ICS URL, or external DB exposure.
- **Next:** open one PR for this branch (do not duplicate #620); run targeted frontend E2E + Python calendar tests via CI, fix failures, require exact HEAD 5/5 Bot checks + 1/1 Tests, inspect source and review threads, merge with `expected_head_sha` only when predecessor main push CI 5/5 and exact PR CI 6/6; then verify new main push CI and automatic Render checksPass exact SHA; read-only production metrics. If pending, leave PR draft and persist next action. Do not claim 100% or perform real mobile acceptance without evidence.
- Strict acceptance remains **1/40 = 2.5%**. A06 and B01 remain unverified; P0 #620 belongs to existing requirements, no denominator change. Daily summary date unchanged (2026-11-01 user-facing reports already exist); no ordinary overnight notification.


## Continuation checkpoint — 2026-11-01 21:25 UTC (PR #621 CI repair)

- Current GitHub `main` and automatic Render LIVE are **`bf899dbda3a219f8759925ff4df7ad8a1955b238`**; Render deploy `dep-dbjqdm6417fc73b807g0` succeeded 2026-11-01 20:55:08 UTC, trigger `new_commit`, `manual=false`. Predecessor main push Bot checks run `41347627625` completed **5/5 SUCCESS**. Render request logs filtered for HTTP 5xx from 20:55–21:25 UTC returned no records; this is not real iPhone/role acceptance.
- P0 iPhone raw ICS bug #620 remains **unreleased**; work continues in existing PR **#621** (`fix/ios-calendar-share-google-fallback-20261102`), not a duplicate. First exact-head CI at `873da830218d3ef4b63f162001f0eac18e77075c`: Bot checks 4/5 SUCCESS, **E2E FAILED**; separate Tests 1/1 SUCCESS. 69/70 Playwright tests passed; the sole failure was legacy `frontend/e2e/readiness-exports.spec.ts` waiting for removed `Добавить в календарь` button. This is a real gate; do not merge failing head.
- Corrected existing desktop readiness export E2E in commit **`cf49f99a8c52c29198ebaffe02fd45f452ea9168`**: check Google Calendar Asia/Yerevan UTC template, click new explicit `Календарь Apple (.ics)` desktop action, retain authenticated ICS UTC response check. New exact-head CI must complete **all 6 SUCCESS** before source review and guarded merge; no rerun of old head substitutes for this.
- Review and production constraints: native Apple share-sheet inside real iPhone Telegram is **Не подтверждено**; Google fallback is offered. No real event #22 edit, test announcement, user/point/registration write, Telegram send, external DB opening, secrets/security settings or manual deploy. 40-item acceptance register remains **1/40 ПРОВЕРЕНО = 2.5%**. #589 and #605 remain high-risk blocked drafts; do not merge as part of calendar repair.
- **Next exact action:** check PR #621 latest HEAD and both CI workflows; if 6/6 SUCCESS, inspect changed code/review threads and merge with `expected_head_sha` only after verifying current `main` and no conflicts. Then main push CI 5/5, automatic Render checksPass exact SHA, safe production smoke, record outcome; next independent task #575/#581 on isolated PG or #589 privacy. No ordinary notification at night; last daily summary date 2026-11-01.


## Continuation checkpoint — 2026-11-01 21:50 UTC (PR #621 guarded merge)

- P0 #620 iOS Telegram raw ICS bug: PR **#621** released to GitHub `main` only, **not yet confirmed Render LIVE**. Final exact HEAD **`06442f803fed03d7761a14489605438b09d6fba6`** passed **6/6 SUCCESS**: Bot checks run `41352185594` (`test`, `postgres-migration`, `secret-scan`, `e2e`, `frontend`), separate Tests run `41352185588` (`test`). Source review: seven changed files, no unresolved review threads; predecessor `main` `bf899dbda3a219f8759925ff4df7ad8a1955b238` was 5/5 push CI and automatic Render LIVE. PR marked ready, mergeable true, merged using **`expected_head_sha`**. New GitHub `main` merge SHA **`1bca3df1f883ea333bd026f034e0415c3060116d`**.
- Final CI repair: updated legacy `readiness-exports.spec.ts` to use explicit Google Calendar and desktop .ics button; corrected accidental doubled regex escapes using a literal digit-class RegExp. New exact-head E2E passed, unlike earlier failed HEAD. No manual deploy or bypass.
- **Release gate pending:** main push CI **5/5 not directly observable through this connector** (its `fetch_commit_workflow_runs` only returns PR-triggered runs; combined statuses endpoint empty is not evidence). At checkpoint, Render `list_deploys` still reports LIVE predecessor **`bf899dbda3a219f8759925ff4df7ad8a1955b238`**, deploy `dep-dbjqdm6417fc73b807g0`; no automatic deployment of new `1bca3df...` observed. Do not claim production fix until exact Render checksPass LIVE and read-only smoke.
- **Next:** (1) verify main push CI through supported run-ID evidence if available; (2) wait for automatic Render checksPass for `1bca3df1f883ea333bd026f034e0415c3060116d`, no manual deploy; (3) check read-only `/health`, `/ready`, logs and HTTP 5xx, and confirm no unauthorized outbound message; (4) review P0 #620 on a real iPhone Telegram WebView with Apple Calendar, plus Android/desktop — **Не подтверждено** until human evidence; (5) continue independent #575/#581 isolated PostgreSQL tests or blocked #589 privacy review, avoid duplicate PRs.
- Register unchanged **1/40 ПРОВЕРЕНО = 2.5%**; #620 is within A06/B01, not a new acceptance denominator. Do not publish `Траектория открытий` 31 Oct, any unapproved ERA message, Mafia, or replay uncertain deliveries. No production events, points, registrations, secrets, security settings, migrations or real Telegram messages changed in this run. Daily summary last sent 2026-11-01; overnight user notification suppressed.


## Continuation checkpoint — 2026-11-01 22:3x UTC (release verification + wizard navigation)

- Reviewed existing checkpoint PR **#623** exact HEAD `c1e58500b371e7d36bf59c00e015239d4a71418b`: 5/5 Bot checks + 1/1 Tests SUCCESS, no unresolved review threads, documentation-only diff. Marked ready and merged with `expected_head_sha`; GitHub main now **`3bbb9308aed47b76e6c14d18dfabc48173ac3bf3`**. New main push CI and exact Render LIVE for this *documentation-only merge* still require confirmation.
- Independently confirmed predecessor **`1bca3df1f883ea333bd026f034e0415c3060116d`** automatic Render LIVE through `dep-dbjrgo3m8hqs73854p30`, successful at 2026-11-01 22:09:47 UTC. Render event confirms `newCommit`, `manual=false`. Filtered request logs 22:09–22:32 UTC returned no 5xx; metrics show 1 instance and near-zero HTTP traffic (one 404 in sampled 22:14 bucket). These are limited production indicators, **not** a verified real iPhone Calendar import or multi-role acceptance. Direct HTTP smoke from this runtime is DNS-blocked; GitHub connector does not expose main push workflow listing.
- New independent frontend branch **`fix/event-wizard-nav-preserve-dirty-20261102`** from `3bbb9308...`: wizard `next()` and `back()` no longer replace the current draft with a stale server response after a user edits fields while the save is pending. Functional `setDraft` updates only `wizard_step` on the same event ID, preserving newer local fields; no backend/DB schema/permissions/Telegram/points changes. Isolated Playwright test delays a real CI draft PATCH response, edits the title while pending, and verifies it survives navigation and re-save. No production event is created by this patch.
- **Next:** create one PR for this frontend branch, run exact-head Bot checks 5/5 and Tests 1/1; if E2E fails, diagnose and fix on the same branch. Source review and guarded merge only when 6/6 SUCCESS, no review blockers, predecessor main CI/release gates confirmed. Then main push CI and automatic Render exact SHA, read-only production checks. Keep #523/#575/#581 scheduler concurrency and #589 listing privacy as separate risk-gated work; avoid duplicate PRs.
- Strict acceptance remains **1/40 ПРОВЕРЕНО = 2.5%**. A06/B01 and actual iPhone Telegram/Apple Calendar, four real user roles, production event list and leadership panel: **Не подтверждено**. No prohibited `Траектория открытий` post, no new ERA messages, Mafia, manual deploy, uncertain resend, real data/points/registration writes, secrets or security-setting changes. Last user-facing daily summary: 2026-11-01; do not send an ordinary overnight notice.


## Continuation checkpoint — 2026-11-01 23:3x UTC (PR #624 merged, save-and-exit guard)

- Current previous main `3bbb9308aed47b76e6c14d18dfabc48173ac3bf3` passed **5/5** GitHub push Bot checks (run `41357664563`), verified via exact commit check-runs REST; Render automatic `dep-dbjs3pjm8hqs7385rbs0` became LIVE at 2026-11-01 22:50:22 UTC, commit matched exactly. This is technical release evidence, **not** multi-role acceptance.
- PR **#624** exact HEAD `6cd0db06522fc42500a86df48274523606f860e4` passed **6/6 SUCCESS** (Bot checks run `41357858374`: test, secret-scan, frontend, e2e, postgres-migration; separate Tests run `41357858397`: test). Inspected 3-file patch and zero unresolved review threads; confirmed mergeable and predecessor main exact SHA, marked ready and merged with `expected_head_sha`. New GitHub main **`2d6b3dbb749c1f1b83d8325a26eee5406173c966`**. At first post-merge check main CI was **in progress** (secret-scan SUCCESS, remaining jobs pending), and Render still LIVE predecessor `3bbb9308...`. Do not claim `2d6b3d...` LIVE until exact automatic Render checksPass.
- New independent branch `fix/event-wizard-leave-pending-edit-20261102`: B01/B04 same event wizard race family. Previously `leaveDraft()` could close the editor after an in-flight save returned even if the user typed newer changes; the older save response did not include those edits. Now a captured `versionRef` guard leaves the editor open and shows a retry message if the draft changed during the save; a concurrent saving state also blocks exit. Added isolated Playwright interception test on a disposable CI draft. No production event/registration/points writes or Telegram sends; no migration, secrets, settings or manual deploy.
- Next: finish exact-head 5/5 Bot checks + 1/1 Tests for this new branch and review, fix test failures on same PR, merge only with `expected_head_sha` after confirming previous main 5/5 and automatic Render LIVE exact SHA. Then verify next main push CI, automatic Render checksPass exact SHA and read-only smoke. Separate high-risk existing drafts #523/#589/#605 remain blocked; do not merge or duplicate them without their safety evidence.
- Strict register unchanged: **1/40 ПРОВЕРЕНО = 2.5%**. Real iPhone Telegram Calendar import, admin/leader/employee/participant scenarios, production event list and leadership panel: **Не подтверждено**. No unauthorized `Траектория открытий` or other ERA publication, no Mafia, uncertain delivery replay, external DB opening or destructive changes. Last ordinary daily summary date 2026-11-01; no overnight notification.


## Continuation checkpoint — 2026-11-02 00:4x UTC (PR #625 merged, exit refresh race)

- Reviewed PR **#625** exact HEAD `e2fe6c3a8a3d8dad4f86507990a7f8996f907afc`: **6/6 SUCCESS** (Bot checks run `41362649257`: test, frontend, e2e, secret-scan, postgres-migration; separate Tests run `41362649240`: test), source patch reviewed and zero unresolved review threads. Predecessor `main` `2d6b3dbb749c1f1b83d8325a26eee5406173c966` confirmed **5/5** exact push check-runs SUCCESS and automatic Render LIVE via `dep-dbjt29dg1s2s738ceiug` (2026-11-01 23:55:34 UTC). PR #625 marked ready, merged using `expected_head_sha`. New GitHub main **`755bb03dab19c6fa658c977120b813fe17859833`**. At first observation, main push checks were still running; new Render LIVE not confirmed. Do not call this SHA production-ready before exact 5/5 and automatic checksPass.
- New independent frontend branch **`fix/event-wizard-leave-list-race-20261102`**: the editor could still close after a slow `listEventDrafts()` refresh even if the user typed newer changes after the initial save. Capture `versionRef` before exit, compare again after the draft-list GET, and retain the open editor plus warning if it changed. Isolated Playwright test delays only CI GET response and edits the current draft during the delay. No production participants/events, Telegram messages, points, migrations, roles, security settings or manual deploy.
- **Next:** open one draft PR for this branch, require exact HEAD 5/5 Bot checks + 1/1 Tests, inspect source and review; confirm predecessor main `755bb03...` 5/5 push CI and automatic Render LIVE exact SHA before guarded merge. Then verify new main CI and automatic Render LIVE plus read-only smoke. If CI fails, repair on same PR; never merge a failed or pending head.
- Existing high-risk drafts #523 (scheduler malformed JSON / #575/#581), #589 (public listing privacy), #605 (legacy naive deadline semantics) and #622 (iOS Telegram delivery) remain independent. #575/#581 cannot be called fixed until isolated PostgreSQL concurrency proof and task/points policy review; do not merge blindly. Real multi-role Telegram, real iPhone Calendar, production event list and leaders panel are **Не подтверждено**.
- Strict acceptance unchanged: **1/40 ПРОВЕРЕНО = 2.5%**. No prohibited `Траектория открытий` or other unauthorized ERA publication, Mafia, uncertain resend, external DB opening or destructive operations. Last ordinary daily summary date 2026-11-01; overnight ordinary notification suppressed.


## Continuation checkpoint — 2026-11-02 ~01:4x UTC (PR #626 release and quick-create mobile)

- PR **#626** exact HEAD `2947a964066c72a610187d5a8f610932f838d3d7` completed **6/6 SUCCESS** (Bot checks run `41368195807`: postgres-migration, secret-scan, frontend, e2e, test; Tests run `41368195745`: test). Source change and Playwright race test inspected, zero review threads/reviews, mergeable against main `755bb03dab19c6fa658c977120b813fe17859833`; marked ready and merged with `expected_head_sha`. New main **`727e7d8a7b02f8a6cb0d908911de939aee17d3cd`**.
- Predecessor main `755bb03dab19c6fa658c977120b813fe17859833` automatically became Render LIVE through `dep-dbju1gtg1s2s738deeb0` at 2026-11-02 01:03:22 UTC. Render service explicitly reports `autoDeployTrigger=checksPass` on branch main, and event `manual=false`. GitHub connector's commit-workflow action filters to PR-triggered runs, and combined commit statuses are empty, so **individual 5/5 main push job results are not directly observable in this runtime**. Render checksPass is a separate positive gate, not a substitute for a claimed direct 5/5 report. New main `727e7d8...` push CI and exact Render LIVE are **not yet confirmed**.
- Next independent low-risk A05/A06/B01 patch on branch `fix/quick-event-mobile-date-time-20261102`: quick-create dialog date/time grid changes from rigid `1fr 1fr` to responsive auto-fit with width-constrained native controls, so 320px Telegram WebView does not clip controls. Added isolated Playwright test `frontend/e2e/event_quick_mobile.spec.ts` for 320px bounding boxes, date/time inputs and no overlap. CI fixture creates only a disposable draft; **never publishes**. No API, migrations, roles, data/points, notifications, security settings or manual deploy.
- **Next:** open draft PR for this branch, verify exact HEAD Bot checks 5/5 + Tests 1/1; inspect code and review. Verify main `727e7d8...` push CI via available authoritative checks and automatic Render checksPass exact SHA; merge new PR only after required gates, with `expected_head_sha`, then new main CI/Render and read-only production smoke. If checks are not observable, record the limitation rather than invent 5/5. Avoid merging #589/#605/#622/#523 without independent safety review.
- Strict acceptance remains **1/40 ПРОВЕРЕНО = 2.5%**; A05/A06/B01 still require real Telegram/mobile and four-role acceptance. Production event list, Apple Calendar, leader panel: **Не подтверждено**. No Mafia, forbidden `Траектория открытий` publication, other unauthorized Telegram messages, uncertain resend, real data mutation, or external database opening. Last ordinary daily summary: 2026-11-01; no overnight ordinary notification.

- PR **#627** opened DRAFT for this quick-create mobile patch, original HEAD `6f6b8d167967a675f3cf7cbf8ec6181f5f61d36e`. First PR CI: Bot checks run `41373902209` queued; separate Tests run `41373902281` in progress at 2026-11-02 ~01:43 UTC. The checkpoint append changes HEAD and therefore requires **fresh exact-head 6/6**; do not reuse previous run statuses. Current main remains `727e7d8a7b02f8a6cb0d908911de939aee17d3cd`, Render still LIVE `755bb03dab19c6fa658c977120b813fe17859833` at the last query. No 5xx request logs returned in 01:03–01:42 UTC filtered interval; limited negative evidence only. No release of #627 yet.


## Continuation checkpoint — 2026-11-02 ~02:35 UTC (PR #627 guarded release, wizard date/time mobile)

- Reviewed PR **#627** exact HEAD `21537e72f6d9cca4ce02ad6dc3e8bd693c6fa6e4`: Bot checks run `41373952086` all five jobs SUCCESS (secret-scan, frontend, e2e, postgres-migration, test); separate Tests run `41373952083` test SUCCESS. Inspected 3-file patch and review threads (none). Predecessor main `727e7d8a7b02f8a6cb0d908911de939aee17d3cd` had 5/5 push Bot checks SUCCESS plus separate verify SUCCESS, and Render automatic checksPass LIVE via `dep-dbjuv5tg1s2s738e9bhg`, finished 2026-11-02 02:05:23 UTC, trigger `new_commit`. Marked #627 ready and merged with `expected_head_sha`; new GitHub main **`645b82e59b2d5b8676c02403319e7474b7a7cf7a`**. At 02:35 UTC its push checks: frontend and secret-scan SUCCESS; e2e, postgres-migration and test IN_PROGRESS. Render still LIVE predecessor `727e7d8...`. Do not claim new main LIVE until 5/5 and automatic exact-SHA Render checksPass.
- Read-only Render request log filter 2026-11-02 02:05–02:35 UTC returned no HTTP 5xx. This is limited evidence, not full production or real mobile acceptance.
- Independent low-risk A05/A06/B01 branch **`fix/event-wizard-date-time-mobile-20261102`**, based on new main `645b82e...`: wizard step 2 previously used rigid `1fr 1fr` for native date and time inputs. Make grid responsive and constrain input widths so both controls stack on 320px Telegram viewport. Add isolated Playwright regression `frontend/e2e/event_wizard_date_mobile.spec.ts`, which creates only a disposable CI draft and never publishes. No API, database, migration, production event, points, registration, messages, secrets, roles, or security settings touched.
- **Next:** create/review a single DRAFT PR for this branch; require exact HEAD 5/5 Bot checks + 1/1 Tests and no review blockers. First verify current main `645b82e...` push CI 5/5 and automatic Render checksPass exact SHA, then guarded merge with `expected_head_sha`, new main CI, exact automatic LIVE, read-only smoke. If CI fails, fix on the same PR; never bypass. High-risk existing #523/#589/#605/#622 remain independent and must not be blindly merged.
- Strict register unchanged: **1/40 ПРОВЕРЕНО = 2.5%**; real iPhone/Android, Apple Calendar import, authenticated production event list, leadership panel, admin/leader/employee/participant acceptance: **Не подтверждено**. No unauthorized publication, prohibited `Траектория открытий` announcement, Mafia, uncertain resend, real user data/points mutation, manual deploy or external DB opening. Last ordinary daily summary 2026-11-01; no overnight ordinary notification.

- **PR #628 opened DRAFT** for the step-2 mobile layout, original HEAD `607a83e01366107af18434517ab96e489f78ce09`. First PR workflows: Bot checks `41378765990` and Tests `41378765978` both IN_PROGRESS at observation; the checkpoint commit changes HEAD and therefore requires **new exact-head 6/6 SUCCESS**. Current main `645b82e...` push CI still has e2e/postgres-migration/test IN_PROGRESS (frontend/secret-scan SUCCESS); Render still LIVE `727e7d8...`. Direct read-only `/health` and `/ready` curl blocked by DNS in this runtime (HTTP 000), so no endpoint success is claimed. Continue on this existing PR, not a duplicate. Do not merge until main 5/5, Render exact LIVE and current PR HEAD 6/6 plus review.
