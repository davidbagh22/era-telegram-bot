# ERA bot and Mini App handoff

- Baseline checked 2026-11-12 Asia/Yerevan: `main` and Render LIVE `f23bfeb40984d86e167f794783d67cfc45df713c`, main CI 5/5. Capacity protection DEPLOYED in [#663](https://github.com/davidbagh22/era-telegram-bot/pull/663).
- E11 webhook authentication and release evidence: [#662](https://github.com/davidbagh22/era-telegram-bot/pull/662). The production startup logs confirm the existing secret configuration. The receiver fails closed and startup skips registration when the secret is missing.
- While #662 is open: verify exact-head CI and merge with the expected SHA. Record main CI, automatic Render LIVE SHA, `/health`, `/ready`, and authenticated webhook startup in the PR after merging.
- B05 remains open for native/Mini App registration policy parity (#514/#510), commit-before-notification (#507), and real Telegram acceptance. #657/#515 were superseded by #663.
- Real iOS/Android and multi-role scenarios: BLOCKED: HUMAN ACCEPTANCE.
- After #662 is LIVE: compare the configured-admin guard in #542 with `main` and recheck the remaining role tests. Check #514 activity before taking registration-policy work.
