# ERA bot and Mini App handoff

- LIVE tip = `d2a8112` (#730 handoff). Prior activation tip = `af43751` (#729). `/health` + `/ready` ok (Europe/Moscow check 2026-11-25 ~09:19 on `af43751`).
- Shipped on that tip chain (not VERIFIED unless noted):
  - #725 feedback eligibility (#585)
  - #726 activity proof commit-before-notice (#529)
  - #727 waitlist points (#513)
  - #728 E09 channel approval UI/commands — **DEPLOYED**; real authorized approval workflow acceptance still open → not VERIFIED
  - #729 anniversary activation + GCal adapter OFF + #582 shared-read docs
- #321 48 laws literature: CODE COMPLETE prep / **not launched**. JSON store `app/content/laws_48_analyses.json` (48 RU analyses, `audio_url=null`). Admin preview `/literature_48_preview` + Mini App `GET /api/v1/workcenter/book-club/laws48-preview` — no public send. Public path gated by `literature_48_laws_publish_enabled=False` **and** existing exact-day series approval. Do not flip the flag or approve launches without owner OK.
- #669 / F01 anniversary: OWNER_RENDER_ACTIVATE on Render writes `ACTIVE_KEY` and scheduler delivers initial posts (past reminder slots skipped). Admin `/activate_anniversary2026` + `/anniversary2026_status` available. **DEPLOYED**, not VERIFIED — channel receipts on @era_leaders1 / announcements topic required before VERIFIED.
- #664 Google Calendar: adapter DEPLOYED, default OFF until Render `GOOGLE_CALENDAR_*` secrets; durable outbox on publish/edit/cancel.
- #582: owner-approved shared-read for media-hub; writes area-scoped (documented + tests).
- Still blocked for full VERIFIED: E14 device/role evidence, E13 #364 legal human, #616 expert platform, GCal credentials. Do not invent legal or device acceptance.
- Campaign/media DM flags remain off unless separately enabled.
