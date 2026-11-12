# ERA bot and Mini App handoff

- Baseline checked 2026-11-12 Asia/Yerevan: `main` and Render LIVE `522f6f135081acb39a803f087b1424e6e352d1f7`, main CI 5/5. Authenticated webhook DEPLOYED in [#662](https://github.com/davidbagh22/era-telegram-bot/pull/662).
- A02 configured-admin boundary and release evidence in [#542](https://github.com/davidbagh22/era-telegram-bot/pull/542). Admin checks require an active database account matching the Telegram sender. Delegated grants are checked against the same identity.
- While #542 is open, verify exact-head CI and merge with the expected SHA. After merging, record main CI, automatic Render LIVE SHA, `/health`, and `/ready` in the PR.
- Real iOS/Android and the admin/leader/employee/participant role matrix are BLOCKED: HUMAN ACCEPTANCE.
- B05 capacity protection DEPLOYED in #663. #514/#510 cover registration-policy parity. #507 covers notification ordering.
- After #542 is LIVE, compare #507 with `main` and finish committing registration changes before Telegram notifications. Check #514 for changes touching the same endpoints.
