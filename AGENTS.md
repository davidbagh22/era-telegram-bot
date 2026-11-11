# ERA bot and Mini App

- Start with `docs/CODEX_HANDOFF.md` and the existing 40 requirements in `docs/AUTONOMOUS_PROGRESS.md`. Read code, history, and pull requests only as needed for the selected requirement.
- Work on one concrete unmet requirement at a time. Check `main` and related open PRs, then reuse an existing PR where practical. Close duplicates only after verifying which changes supersede them.
- Preserve existing user flows. Add targeted regression tests for the defect and require full CI and review on the exact PR head before merging.
- After merging, check `main` CI, the automatic Render LIVE SHA, `/health`, and `/ready`. Do not deploy manually or bypass CI.
- Test with isolated data. Do not send real test broadcasts, edit production user data or roles, expose secrets, or retry uncertain deliveries. Risky migrations require verified reversibility and a backup.
- Keep the handoff short and update it in substantive PRs. Use `NOT STARTED`, `IN PROGRESS`, `CODE COMPLETE`, `DEPLOYED`, `VERIFIED`, or `BLOCKED` in the requirements registry. Real device and role acceptance require direct evidence.
