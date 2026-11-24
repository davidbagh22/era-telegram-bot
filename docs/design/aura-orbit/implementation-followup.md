# AURA × ORBIT follow-through

Continuation of PR #713, no duplicate implementation or release.

Implemented: stable ambient across layout changes/auth; organic stable-hit nodes;
Telegram safe-area bridge + visibility cleanup; real Discover categories;
readable literature archive/issue/subscription using the bot archive bound;
games catalogue respects existing rollout and opens the real bot;
team listing includes accepted memberships; project dates remain tentative;
project list links address actual detail pages and do not auto-open workspace;
people pagination and local orbit/project view preferences.
All project list scopes now use title/date cards; draft deletion remains in
the existing detail confirmation flow. People filters remain available after
empty searches. Team sections offer independent retries and no duplicate cards.

Local validation: typecheck + date-only TZ check + build PASS;
61 existing literature/project/security tests, 5 new leisure/team tests and
14 auction regressions PASS (80 targeted tests total). Tests require the CI
dummy BOT_TOKEN; the initial broader local invocation omitted it and is not
a passing full-suite result. Full CI on the final head remains required.
JS gzip 238.54 kB vs PR baseline 235.42 kB; CSS gzip 6.62 vs 5.86 kB.

CI E2E is configured to produce mobile screenshots and motion recordings as
aura-orbit-visuals. It has not run on the new local implementation yet.
Local Chromium launch is blocked by the execution environment's socket() policy;
this is not successful browser acceptance. iOS/Android Telegram acceptance stays
unverified. No production users, subscriptions, broadcasts or roles changed.

Full registered screen-file inventory: screen-inventory.csv.

Release status: BLOCKED before publishing. The implementation is committed
locally for existing PR #713. Automatic approval review rejected the git push
because the repository is public and the current request authorizes local work
without explicit authorization to publish source there. No workaround, merge
or deployment performed. Remote PR head remains 952f8e08. Owner authorization
to publish is required before exact-head CI, review and automatic deployment.
