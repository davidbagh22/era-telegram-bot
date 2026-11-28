# ERA bot and Mini App handoff

- LIVE tip = `399ce84` (#746 short bot menu + light admin home, after #742–#745). `/health` + `/ready` ok; single Alembic head `0070_user_ui_preferences`.
- Current PR (`cursor/admin-command-center-6c4a`, no DB migration): Admin Command Center on Mini App admin home (top quick actions: Рассылка → BroadcastPanel, Задание → open task form, Мероприятие → create event; immediate KPI & analytics summary with drill-down; in-app Decision Queue with server-side admin-only soft-delete, confirmation, AuditLog, and undo/restore) plus bot admin hub quick `📨 Рассылка` / `📊 Статистика` buttons and live KPI summary.
- Shipped on prior tip chain (not VERIFIED unless noted):
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
