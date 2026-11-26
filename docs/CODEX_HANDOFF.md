# ERA bot and Mini App handoff

- LIVE = `af43751` (#729 activation wave). `/health` + `/ready` ok (Europe/Moscow check 2026-11-25 ~09:19).
- #565 Render LIVE stale monitor: CODE COMPLETE — schedule-only GH workflow + in-app classifier reuse `render_release_lag`; admin DM gated by `FEATURE_RENDER_LIVE_STALE_ALERTS` (default OFF) via `safe_send_once`. Not a checksPass gate; exact LIVE still needs Render API secret on the Actions job.
- #669 anniversary: OWNER_RENDER_ACTIVATE on Render writes `ACTIVE_KEY` and scheduler delivers initial posts (past reminder slots skipped). Admin `/activate_anniversary2026` + `/anniversary2026_status` available. Channel receipts → claim VERIFIED only with evidence.
- #664 Google Calendar: adapter DEPLOYED, default OFF until Render `GOOGLE_CALENDAR_*` secrets; durable outbox on publish/edit/cancel.
- #582: owner-approved shared-read for media-hub; writes area-scoped (documented + tests).
- Still blocked for full VERIFIED: E14 device evidence, #364 legal human, #616 expert platform, GCal credentials. Do not invent legal acceptance.
- Campaign/media DM flags remain off unless separately enabled.
