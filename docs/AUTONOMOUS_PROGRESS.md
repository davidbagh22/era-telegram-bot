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
| A06 | iPhone and Android Mini App | В РАЗРАБОТКЕ | Real Telegram clients, not only Playwright |
| B01 | Event create/publish/edit | ВЫПУЩЕНО | Real authorized scenario, no test announcement |
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
