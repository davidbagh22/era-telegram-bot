# ERA bot and Mini App handoff

- LIVE tip = `d2a8112` (#730 handoff). Prior activation tip = `af43751` (#729). `/health` + `/ready` ok (Europe/Moscow check 2026-11-25 ~09:19 on `af43751`).
- Shipped on that tip chain (not VERIFIED unless noted):
  - #725 feedback eligibility (#585)
  - #726 activity proof commit-before-notice (#529)
  - #727 waitlist points (#513)
  - #728 E09 channel approval UI/commands — **DEPLOYED**; real authorized approval workflow acceptance still open → not VERIFIED
  - #729 anniversary activation + GCal adapter OFF + #582 shared-read docs
- #669 / F01 anniversary: OWNER_RENDER_ACTIVATE on Render writes `ACTIVE_KEY` and scheduler delivers initial posts (past reminder slots skipped). Admin `/activate_anniversary2026` + `/anniversary2026_status` available. **DEPLOYED**, not VERIFIED — channel receipts on @era_leaders1 / announcements topic required before VERIFIED.
- #664 Google Calendar: adapter DEPLOYED, default OFF until Render `GOOGLE_CALENDAR_*` secrets; durable outbox on publish/edit/cancel.
- #582: owner-approved shared-read for media-hub; writes area-scoped (documented + tests).
- Still blocked for full VERIFIED: E14 device/role evidence, E13 #364 legal human, #616 expert platform, GCal credentials. Do not invent legal or device acceptance.
- Campaign/media DM flags remain off unless separately enabled.
- Post-event certificates (owner request): after an event ends (≤3 days), owner + responsible get a bot notice and choose recipients in `/event_certificates`; nothing is issued or sent until confirmed. Flag `POST_EVENT_CERTIFICATE_REVIEW_ENABLED` (default on). Older past events: one-time backfill in a follow-up PR. **CODE COMPLETE**, real owner acceptance open.
