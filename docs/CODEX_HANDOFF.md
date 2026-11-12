# ERA bot and Mini App handoff

- Last confirmed baseline before #497 was `107f23690aedf35ad426ef5f5bab1869efea71e0` on `main` and Render LIVE. Main CI passed 5/5 and both health endpoints returned 200. [#514](https://github.com/davidbagh22/era-telegram-bot/pull/514)
- B05 registration and waitlist notices are queued with the business transaction and claimed after commit. The worker recovers queued notices after restart and keeps uncertain outcomes for reconciliation. [#497](https://github.com/davidbagh22/era-telegram-bot/issues/497)
- Check #497's linked PR for exact-head CI, main CI, automatic Render LIVE SHA, `/health`, and `/ready` evidence.
- B05 remains IN PROGRESS for the waitlist scoring decision in #513. Telegram registration and waitlist scenarios are BLOCKED: HUMAN ACCEPTANCE.
- Next, compare the poster access and content-type changes in [#484](https://github.com/davidbagh22/era-telegram-bot/pull/484) with `main` and overlapping [#486](https://github.com/davidbagh22/era-telegram-bot/pull/486). Continue with the first remaining E11 fix.
