# ERA bot and Mini App handoff

- Owner priority (13 November): anniversary RSVP, 12 December 2026 at 17:30 Asia/Yerevan, cinema hall of Moscow House in Yerevan.
- Branch `feat/anniversary-2026-rsvp`: dedicated `/start anniversary2026` guest flow before generic onboarding; first name, surname, organization, explicit confirmation/consent. No membership creation, points, subscription requirement, broadcast or migration.
- AppSetting guest key is unique by Telegram sender; database upsert does not overwrite or duplicate existing registrations and commits before confirmation. Admin-only `/anniversary_guests` CSV export protects spreadsheet formulas.
- Local targeted tests pass; full final-head CI, guarded merge, main CI and automatic Render LIVE are still required. Do not distribute the link as working before deployment: https://t.me/ERA_1bot?start=anniversary2026.
- Last checked main before this work: 55c9c8cb9f60296bfc72dc702bcde4341feea1a5 (#666). See #666 for its exact release evidence.
- Existing B05 waitlist scoring #513 and E11 poster access #484/#486 remain; real multi-role/device acceptance is still unconfirmed. No changes to those policies in this RSVP task.
