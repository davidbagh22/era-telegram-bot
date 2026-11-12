# ERA bot and Mini App handoff

- Baseline checked 2026-11-12 Asia/Yerevan: `main` and Render LIVE `38dd9261ebc794793f56e4c96b963a21cfa59f65`, main CI 5/5. Configured-admin protection DEPLOYED in [#542](https://github.com/davidbagh22/era-telegram-bot/pull/542).
- B05 notification ordering and release evidence in [#507](https://github.com/davidbagh22/era-telegram-bot/pull/507). Mini App and native Telegram registration/cancellation commit before sending success or waitlist notices. The current committed state is checked before delivery.
- While #507 is open, verify exact-head CI and merge with the expected SHA. Record main CI, automatic Render LIVE SHA, `/health`, and `/ready` in the PR.
- Durable recovery of an interrupted registration notice remains open in #497. Capacity protection is DEPLOYED in #663.
- Real Telegram registration, waitlist and role scenarios are BLOCKED: HUMAN ACCEPTANCE.
- After #507 is LIVE, compare #514 with `main` and finish registration deadline and waitlist policy under the existing event-row lock.
