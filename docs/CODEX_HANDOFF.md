# ERA bot and Mini App handoff

- 18 November / **PARALLEL GO-TO-READY** (`docs/TZ_PARALLEL_READY_2026_11_18.md`): never idle on one CI; parallel workstreams for UX/waves/security/matrix. Goal: code+CI+LIVE ceiling ASAP; E14 human acceptance remains separate.
- 18 November / portfolio visual v2 **CODE COMPLETE** (`cursor/era-portfolio-visual-v2-37e0`, #690): TZ `docs/TZ_PORTFOLIO_VISUAL_2026_11_18.md` — dark teal hero, two-column rail, entry cards, canvas-pinned signatures; sparse placeholders. Samples `/opt/cursor/artifacts/portfolio_era_{visual,sparse}_v2.png`. Rebased onto main → CI → merge → LIVE.
- 18 November / project covers: `cover_bytes` + Mini App `object-fit: contain` (no crop). Migration `0065_project_cover`.
- 18 November / attendance proofs in «Решить сегодня» **LIVE `63d5d83`**: `/health`+`/ready` ok; photo proofs queue (approve → points+cert).
- 17 November / portfolio PDFs + export interview **LIVE `f778f6d`**: teal letterhead PDFs; export interview for skills/about; events + certificates first.
- 17 November / attendance-certs-media **LIVE `9a9d084`**: owner TZ — auto participation PDF + seal, media briefs, contain posters, afisha cutoff, cert ladder 2000/5000.
- 17 November / ERA 2.0 UX stack (#676/#677/#679): participant UI renames «ЭРА PRO» → «Лидеры ЭРА»; hide raw `public_activity` keys; profile history = attended/results only, registrations separate; «Сейчас» calendar drops past items; tasks scopes label «Доступные»; auto-archive + media titles + welcome-chat routing on upstack. Rebased onto main; merge when CI green.

- 17 November / wave-4 (stacked): Admin queue retitled «Решить сегодня»; media request packages (фото/рилс/полный) + due_at; Leader media-request panel. Depends on wave-3.
- 17 November / wave-3 (stacked): assessment complete → +25 digital points; result card «Твой профиль ЭРА» with share + event CTA + unlock ladder. Depends on wave-2.
- 17 November / wave-2 (stacked): Admin «Назначить руководителя» with function packages; Profile «Предложить в руководство»; Leader hub retitled + media-request tile. Depends on wave-1 merge.
- 17 November / wave-1 product PR: teal+white air theme (anti-purple), haptic on primary CTAs, compact Home + ranks hub, Home «Узнай профиль · 3 мин», simplified bot reply keyboard (Лидеры/Медиа only with rights). Owner approved proposals 1–22,24–30; #23 bot admin freeze skipped. Remaining after wave-1–4 merge: weekly insight polish, onboarding 3 steps, friend compare, referral-to-event, acceptance matrix. Do not claim LIVE until exact-head merge + Render SHA + device check.
- 16 November / #673: Home shows upcoming published events. The existing bot-owned registration pin exposes direct board, personal events and profile links. The registration confirmation links to personal events. Verify exact-head CI, automatic LIVE and the click-through on iPhone and Android.

- 14 November: existing 12 December anniversary (screenshot title «12 декабря для ЭРА — особенная дата.») is featured above the Mini App home feed and first in the native bot reply menu. Mini App also registers from the participation card. Complete profile uses one tap, missing fields are collected in context.
- New anniversary entries from either surface use the existing guest RSVP store. Previous event registrations keep their status and appear in the deduplicated `/anniversary_guests` export. This change uses the existing event and does not activate the #670 publication/reminder campaign.
- Verify the exact PR head, main CI and automatic Render LIVE. Confirm the live event matches by date, start time and title or existing campaign marker. Keep production writes limited to genuine user actions.

- Owner priority (13 November): anniversary RSVP, 12 December 2026 at 17:30 Asia/Yerevan, cinema hall of Moscow House in Yerevan.
- #667 guest RSVP deep link `/start anniversary2026` and #668 event photo/direct links are already in main. Last verified Render LIVE before this change: `75f52fd952cc51ecf81ef64753511b58b6dcbfff`, deploy `dep-dbrnldff3r2c7391pe20`.
- AppSetting guest key is unique by Telegram sender; database upsert does not overwrite or duplicate existing registrations and commits before confirmation. Admin-only `/anniversary_guests` CSV export protects spreadsheet formulas.
- Existing B05 waitlist scoring #513 and E11 poster access #484/#486 remain; real multi-role/device acceptance is still unconfirmed. No changes to those policies in this RSVP task.
