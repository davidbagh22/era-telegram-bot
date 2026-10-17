# ERA verification — 10 October 2026, Asia/Yerevan

Status: **not accepted as complete production**. This is an evidence log, not a clean bill of health.

## Production evidence obtained read-only

- Render service `srv-d91r1j7avr4c73fs8h00` was live on `d35650cbcceb4325495d745d4abad29c5066fc38` (PR #318), not on #322/#323.
- Auto-deploy in the live service is triggered by commits. The repository Blueprint says `checksPass`; the deployed configuration differs. Do not assume the YAML controls the existing resource.
- Notifications topic is persisted as thread `26206`; Announcements as `26205`. Both belong to the configured general chat.
- Key Value `red-d91r19navr4c73fs831g` is **suspended**, plan free, persistence off. Production startup log explicitly reports `FSM_STORAGE_MODE=memory`. A process restart therefore loses unfinished in-memory dialogs. No configuration was changed in this verification.
- PostgreSQL is available, version 18, basic_256mb, 1 GB, external allow-list `0.0.0.0/0`. Restricting it requires identifying authorized backup/admin clients first; do not cut these off blindly.
- Read-only SQL found **zero duplicate (event_id,user_id) registration pairs**. Existing uniqueness constraint and event row locks are present in code.
- Notification ledger at inspection: 582 sent, 8 blocked. This is a transport count, not unique active users or engagement.
- Latest five backup-history entries were successful and contained restore verification timestamps. Latest proof: [workflow 37898602546](https://github.com/davidbagh22/era-telegram-bot/actions/runs/37898602546), job `backup-and-verify`, all relevant steps successful including isolated PostgreSQL restore, migration-head verification, encryption round-trip and encrypted artifact upload. External object-storage copy was skipped. This proves that snapshot restoration, not every possible future recovery scenario.
- Logs repeatedly report failure to set default writable permissions in the general chat. Topic existence alone does not prove every required bot permission.

## Changes and tests

| PR | Change | Evidence at preparation | Acceptance still needed |
|---|---|---|---|
| #323 | HTML and actual one-time announcement; prevent automatic retry of uncertain sends and expired claims | 32 local tests, 6 subtests; Bot checks green including E2E, migrations, dependency and secret scans | Remaining workflow, merge, live SHA, persisted `general-topic:notifications:era-directions-invite-v1` status sent |
| #324 | Remove startup FLUSHDB; Redis timeouts; real Redis persistence integration in CI | 15 local tests and 7 subtests; one local Redis test skipped; Bot checks green | Resume persistent Redis, verify URL and storage mode, verify production dialog after restart |
| #322 | 48 distinct critical readings, original corrected title ordering, private catalogue, explicit reading/task self-report, subscription and opt-out, Yerevan schedule | 25 targeted tests; literature suite rerun after concurrent title integration (6 passed); lint | Full CI, merge after #323, active menu verification, a consenting test recipient and opt-out verification |
| #325 | Commit personal broadcast campaign before send, fixed audience, stable confirmation keys, per-recipient ledger, resume worker, archive exclusion | 39 broadcast tests; scheduler regression; frontend typecheck/build; lint | Full CI; merge after #323; direct-chat composer idempotency remains outside this fix |

An additional **61 tests** passed for event creation/persistence, registrations, API authentication/authorization and backup recovery. They use isolated data; no test campaigns or fake events were sent to the live community.

## Explicitly open risks and gates

1. **P0:** Redis is still suspended. Do not mark FSM durable based on code or a local/CI Redis test. Repeated releases while production uses MemoryStorage erase current dialogs.
2. **P0 verification:** Live administrator Telegram event creation and real RSVP end-to-end were not performed. Automated tests are evidence for code behavior, not an impersonated user session.
3. **P1:** Direct-to-chat administrative composer still lacks stable confirmation keys. The new personal-campaign queue does not fix that separate path.
4. **P1:** A complete handler/API/IDOR audit and validation of all effective role scopes is not finished. Existing negative tests and secret scans do not establish absence of all security defects.
5. **P1:** Restrict public PostgreSQL ingress after confirming the backup/admin path; verify actual TLS/session configuration without disclosing credentials.
6. **P1:** Restore persistent Redis through the existing resource, or explicitly review a replacement/cost change. Available Render connector exposes read/create operations but no resume/update operation for this existing Key Value instance; CLI credentials were unavailable.
7. **P2:** Do not call self-reported reading/task marks verified learning, unique recipients active membership, or delivered messages engagement. No synthetic points are added by literature.
8. **P2:** Cohort retention, activation funnel, profile correctness and representative UX pilot remain unverified. Do not invent baseline values.

## Release sequence

After operational Redis blocker is resolved, require green checks for the exact heads; merge #323, #324, #322, #325 with integration checks for the combined main tree, avoiding unreviewed interleaving from other sessions. Confirm final Render commit, health and error logs. Verify ledger evidence for the user-authorized directions announcement; do not resend if outcome is uncertain. Check subscription and unsubscribe using a consenting test user. Keep #319 draft until its remaining audit gates are actually complete.

No credentials, message payloads containing PII or database snapshots are included in this report.
