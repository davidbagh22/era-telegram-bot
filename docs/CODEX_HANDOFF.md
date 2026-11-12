# ERA bot and Mini App handoff

- Baseline checked 2026-11-12 Asia/Yerevan: `main` and Render LIVE `fb307066cd2ef6ce37a8d7812c40ef53b136052d`, main CI 5/5. Commit-before-notice DEPLOYED in [#507](https://github.com/davidbagh22/era-telegram-bot/pull/507).
- B05 registration policy and release evidence in [#514](https://github.com/davidbagh22/era-telegram-bot/pull/514). Mini App and native Telegram enforce current deadline, registration-required, capacity and waitlist settings under the event lock used by the admin editor.
- While #514 is open, verify exact-head CI and merge with the expected SHA. Record main CI, automatic Render LIVE SHA, `/health`, and `/ready` in the PR.
- Capacity protection is DEPLOYED in #663. The waitlist scoring decision remains in #513.
- Real Telegram registration, waitlist and role scenarios are BLOCKED: HUMAN ACCEPTANCE.
- After #514 is LIVE, check #497 for transaction-coupled recovery of interrupted registration notices using existing delivery receipts for deduplication.
