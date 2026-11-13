# ERA bot and Mini App handoff

- #669: anniversary publication implementation. Original IMG_3322.PNG is bundled unchanged (SHA256 6bc159a980bad0ec7cf27d23957add7a75dd42a4c22b37c948735719bc7d88c0).
- ANNIVERSARY_2026_CAMPAIGN defaults off. After exact-head/main CI and automatic Render LIVE, prepare creates exactly one event plus 18 durable delivery intents; publish enables the two initial posts and eight dated reminders per target. Existing candidate events fail closed for reconciliation.
- Destinations resolve from active channel configuration and existing general_forum announcements topic, then freeze in AppSetting anniversary:2026:campaign. Existing safe_send_once ledger owns receipts; unknown outcomes are never replayed. No guest/member writes or private broadcasts.
- Event marker routes bot/Mini App registration to existing /start anniversary2026. Generic event registration is rejected. /anniversary_guests remains the only guest roster.
- ANNIVERSARY_669 log contains event ID, original poster checksum, target IDs, dates and real delivery message IDs. CI/LIVE and actual publication evidence will be recorded in #669. Do not declare success from this handoff alone.
- Prior requirements and role acceptance remain in docs/AUTONOMOUS_PROGRESS.md; no other campaign is authorized by this work.
