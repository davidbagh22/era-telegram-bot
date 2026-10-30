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
