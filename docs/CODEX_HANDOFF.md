# ERA bot and Mini App handoff

- 24 November / release unblock (owner registry): 18/40 shipped-or-checked (45%), 3/40 fully accepted (7.5%); LIVE=`aaf7cdbe`=main tip; 10 open PRs. P0: finish #723 → rebase #670 anniversary → security/QR/points. Stop feature sprawl; merge+test+ship only.
- 24 November / #723 (`b45dd720`): Codex P2 closed — permanent topic-close failures → `attention`+clear due queue; wizard omits unchanged `topic_close_at`. Await CI then owner merge (no manual Render).
- Event management: published cards open a role-gated details editor. The home orbit opens assessments. Release and Telegram device acceptance pending.
- Release scope includes project topics, scoped recipient preview, notice routing, attendance certificates and the four November events. Reconcile any uncertain Telegram creation before retrying.
- 19 November / AURA×ORBIT follow-through prepared locally for #713: persistent ambient above layouts/auth, organic blue-glass nodes, actual Discover/reading/game-gated surfaces, own+accepted team memberships, project title/date cards in every list scope and explicit workspace entry. Local typecheck/build PASS; 80 targeted tests PASS (CI dummy BOT_TOKEN required). New E2E is configured to record screenshots/video in CI; local Chromium is BLOCKED by socket() policy, so no local browser/device VERIFIED claim. Public git push was rejected by automatic approval review pending explicit owner authorization; PR remote head remains 952f8e08, no merge/deploy.

- 19 November / **AURA×ORBIT redesign** (`cursor/aura-orbit-redesign-37e0`, #713, CI green `b5a17664`+): Stage A–C CODE COMPLETE; Stage D CODE COMPLETE for shared accents (Card/PillTabs/ActionCell/ProgressRing/SignalGlow/Vector*/admin panels → AURA primary/cyan). Remaining Stage E: screenshots/build delta + device VERIFIED. Coverage: `docs/design/aura-orbit/coverage.csv`.
- 19 November / literature recovery (#711 `2fa6c9a5`, CI green, MERGEABLE): root cause = empty `APPROVED_SCHEDULED_*` after #649 (LIVE still `57c4108`, issue ~41); DB AppSetting approve/revoke; editorial-enabled → status «Нужна проверка»; games cards + mid-round return; mode-notification job wired; dead `cabinet_keyboard` removed. Blockers: merge→LIVE editor approve for message_id; device Telegram/role matrix; full module audit incomplete.
- 19 November / literature recovery (`cursor/literature-games-audit-37e0`): root cause = empty `APPROVED_SCHEDULED_LITERATURE_ISSUES` after #649; DB AppSetting approvals + /literature_admin series preview/approve/revoke; no missed-day catch-up. LIVE was 57c4108.
- 18 November evening / merge wave: #699/#702 on main; rebasing #700–#708 for squash merge. E14 human acceptance still required.
- 18 November / UX feed dedupe (#699 merged): poster-first feed + meta strip + «Открыть событие» e2e label.
- 18 November / tasks+vector+portfolio (`cursor/tasks-vector-portfolio-37e0`, #700): task cards «Взять»+«Подробнее»; PDF modes; include_in_resume privacy; legacy confirmed_items in career PDF.
- 18 November / CONTENT bot RU (#702 merged): tighten AI-template voice in `texts.py` / `ux_texts.py`.
- 18 November / E11 security (#691): CANCELLED event detail/poster privacy — public allowlist + Mini App detail/poster 404 unless registered. Complements #484.
- 18 November / cleanup (#692): remove proven-dead unmounted handlers/stubs + unused Mini App components + dead `project:hint` keyboard path. No queues/roles/points/history/secrets touched.
- 18 November / #675: Home separates participant growth progress from «Мой вектор».
- 18 November / **PARALLEL GO-TO-READY** (`docs/TZ_PARALLEL_READY_2026_11_18.md`): never idle on one CI; parallel workstreams for UX/waves/security/matrix. Goal: code+CI+LIVE ceiling ASAP; E14 human acceptance remains separate.
- 18 November / portfolio visual v2 **CODE COMPLETE** (`cursor/era-portfolio-visual-v2-37e0`, #690): TZ `docs/TZ_PORTFOLIO_VISUAL_2026_11_18.md` — dark teal hero, two-column rail, entry cards, canvas-pinned signatures; sparse placeholders. Samples `/opt/cursor/artifacts/portfolio_era_{visual,sparse}_v2.png`. Rebased onto main → CI → merge → LIVE.
- 18 November / project covers: `cover_bytes` + Mini App `object-fit: contain` (no crop). Migration `0065_project_cover`.
- 18 November / admin UX follow-up (`cursor/admin-ux-waitlist-media-37e0`): «Решить сегодня» waitlist opens participants/operations (not events menu); leader media-request panel shows numbered package steps and hides past events. Prior #698 (`cursor/admin-ux-fix-37e0`) already on main.
- 18 November / admin UX (`cursor/admin-ux-fix-37e0`, #698 merged): «Решить сегодня» event/project queues open concrete resolvers; appoint-leader keeps selected person/`expected_role`; leader overview task status labels.
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
