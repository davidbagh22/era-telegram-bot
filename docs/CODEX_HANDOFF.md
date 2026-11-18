# ERA bot and Mini App handoff

- 18 November / CONTENT bot RU (`cursor/content-bot-ru-voice-37e0`): tighten AI-template voice in `texts.py` / `ux_texts.py` (menus, empty states, registration, portfolio, departments). Mini App leftovers already covered by #697; no behavior/roles/points changes.
- 18 November / E11 security follow-up (`cursor/security-ecc-hardening-bd19`): CANCELLED existence oracles closed on Mini App register/cancel/activities (same 404 gate as #691 detail/poster). Anniversary guest CSV remains admin-only; referrals return counts only; portfolio/career downloads stay owner-scoped.
- 18 November / E11 security (#691): CANCELLED event detail/poster privacy — public allowlist + Mini App detail/poster 404 unless registered. Complements #484.
- 18 November / cleanup (#692): remove proven-dead unmounted handlers/stubs + unused Mini App components + dead `project:hint` keyboard path. No queues/roles/points/history/secrets touched.
- 18 November / #675: Home separates participant growth progress from «Мой вектор».
- 18 November / **PARALLEL GO-TO-READY** (`docs/TZ_PARALLEL_READY_2026_11_18.md`): never idle on one CI; parallel workstreams for UX/waves/security/matrix. Goal: code+CI+LIVE ceiling ASAP; E14 human acceptance remains separate.
- 18 November / portfolio visual v2 **CODE COMPLETE** (`cursor/era-portfolio-visual-v2-37e0`, #690): TZ `docs/TZ_PORTFOLIO_VISUAL_2026_11_18.md` — dark teal hero, two-column rail, entry cards, canvas-pinned signatures; sparse placeholders. Samples `/opt/cursor/artifacts/portfolio_era_{visual,sparse}_v2.png`. Rebased onto main → CI → merge → LIVE.
- 18 November / project covers: `cover_bytes` + Mini App `object-fit: contain` (no crop). Migration `0065_project_cover`.
- 18 November / admin UX (`cursor/admin-ux-fix-37e0`): «Решить сегодня» event/project queues open concrete resolvers; appoint-leader keeps selected person/`expected_role`; leader overview task status labels.
- 18 November / attendance proofs in «Решить сегодня» **LIVE `63d5d83`**: `/health`+`/ready` ok; photo proofs queue (approve → points+cert).
- 17 November / portfolio PDFs + export interview **LIVE `f778f6d`**: teal letterhead PDFs; export interview for skills/about; events + certificates first.
- 17 November / attendance-certs-media **LIVE `9a9d084`**: owner TZ — auto participation PDF + seal, media briefs, contain posters, afisha cutoff, cert ladder 2000/5000.
- 17 November / ERA 2.0 UX stack (#676/#677/#679) merged to main: «Лидеры ЭРА», history vs registrations, «Сейчас» without past; auto-archive/media titles; welcome chats + PRO/RU cleanup. Await Render LIVE SHA = main tip.
- 17 November / #674 merged: full event posters, readable copy, full nav labels; portfolio hides cancelled/rejected authored projects.
- Production DB read: screenshot events «1» / «й» / «Последний хранитель…» absent. Cancelled test projects 19/20/21 recorded as cleaned earlier — do not re-delete.

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
