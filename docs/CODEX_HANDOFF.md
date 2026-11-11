# ERA bot and Mini App handoff

- Baseline checked 2026-11-12 Asia/Yerevan: `main` and Render LIVE `759b1ad435c7b12d3a5c643aa78996f469762524`, main CI 5/5, `/health` and `/ready` 200.
- B05 capacity and waitlist concurrency: [#663](https://github.com/davidbagh22/era-telegram-bot/pull/663) is the current release candidate. Registration and promotion share the event-row lock, refresh capacity after acquiring it, and lock the event before any pending cancellation is flushed.
- While #663 is open: verify exact-head CI and merge with the expected SHA. Record main CI, automatic Render LIVE SHA, `/health`, and `/ready` in the PR after merging.
- B05 remains open for native/Mini App registration policy parity (#514/#510), commit-before-notification (#507), and real Telegram acceptance. #657/#515 overlap the capacity fix.
- E11 webhook hardening (#662): release depends on confirming the production webhook secret is configured without reading or exposing its value.
- Real iOS/Android and multi-role scenarios: BLOCKED: HUMAN ACCEPTANCE.
- After #663 is LIVE: check the webhook release condition, then compare #514 with `main` for native/Mini App deadline and waitlist parity.
