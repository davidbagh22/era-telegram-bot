# Bot vs. Mini App — Role Separation Audit

**PR 36.** Written before touching any UX, per the project owner's brief:
"Проведи полный аудит Telegram-хендлеров и Mini App. Для каждой функции
ответь: нужна ли она в Bot; нужна ли она в Mini App; является ли она
дубликатом; где должен находиться основной UX."

This is the map that grounds PR 36–42. It does not delete anything by
itself — PR 36 only changes what the bot's default UX *advertises*
(`app/keyboards/participant.py`'s `main_menu()`/`main_inline_keyboard()`);
every "duplicate, Bot code becomes fallback-only" row below still has its
full handler code intact until a later, verified cleanup pass (PR 41), per
the owner's own instruction not to delete old logic before confirming the
Mini App equivalent is stable.

**Ground truth at time of writing**: `app/handlers/` is ~17,600 lines
across participant (5,534), leader (2,125), and admin (9,912, of which
`panel.py` alone is 4,192). `frontend/src/screens/` is ~5,700 lines and
already covers Home, Activity (Events/Tasks/Calendar/History), Projects +
Project Workspace, Opportunities (catalog/auctions/surveys/rewards),
Profile + Portfolio, Leader Mode, and Admin Mode (dashboard, applications,
project/event moderation, task review, offer/reward/auction review,
people, offices, surveys) — the original 12-PR plan plus PR 29–35's
feature-parity work. The Mini App side of this audit is "does the feature
already exist," not "does it need to be built" — it does, everywhere
except the two gaps called out below.

## Legend

- **Bot** — should the bot keep this as a real, reachable feature.
- **Mini App** — does the Mini App already have a full, stable equivalent.
- **Primary UX** — where the day-to-day interaction should happen once
  both exist.

## Participant surfaces

| Feature | Bot | Mini App | Duplicate? | Primary UX |
|---|---|---|---|---|
| Registration / onboarding FSM (`registration.py`) | ✅ keep | n/a (can't apply before having an account) | no | Bot |
| Subscription-gate / pending-approval messages (`start.py`) | ✅ keep | Mini App shows `PendingScreen` once logged in, but login itself needs an approved account | no | Bot (pre-account), Mini App (post-account status) |
| `👤 Личный кабинет` menu tree (`cabinet.py`, `cabinet_hubs.py`, `navigation.py`, `growth.py`, `journey_keyboard`/`profile_sections_keyboard`/`points_hub_keyboard`) | fallback only | ✅ `ProfileScreen` (profile, points, achievements, portfolio, projects, departments) | **yes, fully** | Mini App |
| Profile editing (`profile_settings.py`) | fallback only | ✅ `ProfileScreen`'s edit flow | **yes, fully** | Mini App |
| Portfolio view/upload/PDF (`cabinet.py`'s portfolio/resume handlers) | fallback only, file *upload* stays Bot (see below) | ✅ Portfolio section of `ProfileScreen` | **yes, view; upload is a real Bot-only step** | Mini App for browsing; Bot FSM only for the actual file send |
| Points / balance / rating (`point_transfer.py`, `cabinet.py`'s points/rating handlers) | fallback only | ✅ Home + Profile show balance; `cabinet:rating` has no direct Mini App leaderboard equivalent yet | mostly yes | Mini App (rating leaderboard is a known gap, not a blocker — see PR 38 notes) |
| Events / "Афиша" browsing (`events.py`, `events_stability_block8.py`) | fallback + notifications | ✅ Activity → Events tab | **yes, fully** | Mini App |
| Event registration (`event_plans_changed.py`, event-join callbacks) | fallback | ✅ `EventsTab`'s register/cancel | **yes, fully** | Mini App |
| Event photo/attendance proof upload (`project_event_photo_flow.py`, `leader_event_photo.py`) | ✅ keep (upload) | Mini App links out via deep link, doesn't re-implement upload | no (by design) | Bot FSM, entered from a Mini App deep link |
| Event Activities proof submission (`event_activities_block15.py`/`block7.py`) | ✅ keep (upload) | ✅ Activity panel shows/reviews; submission hands off to Bot via deep link (PR 32) | no (by design) | Mini App for browsing/review, Bot FSM for the actual proof upload |
| Tasks — browse/join (`task_block2.py`) | fallback + notifications | ✅ Activity → Tasks tab | **yes, fully** | Mini App |
| Task result submission (`task_reply.py`, `_try_start_task_submission_from_deep_link`) | ✅ keep (upload) | Mini App links out via deep link | no (by design) | Bot FSM, entered from a Mini App deep link |
| Projects — browse/create/edit/submit (`projects.py`, `projects_block5.py`, `project_hints_addon.py`) | fallback | ✅ `ProjectsScreen` + `ProjectWorkspace` (797 lines — the most complete Mini App screen in the repo) | **yes, fully** | Mini App |
| Project Workspace (team, milestones, tasks) | fallback | ✅ `ProjectWorkspace.tsx` | **yes, fully** | Mini App |
| Opportunities / partner offers (`partner_offers_block16.py`, `partners.py`) | notification + fallback | ✅ `OpportunitiesScreen` catalog + apply flow | **yes, fully** | Mini App |
| Auctions (`auction_block17.py`) | fallback | ✅ `opportunities/AuctionsPanel.tsx` | **yes, fully** | Mini App |
| Rewards / redemptions (PR 31) | fallback | ✅ `opportunities/RewardsPanel.tsx` | **yes, fully** | Mini App |
| Surveys (PR 29) | notification + fallback | ✅ `opportunities/SurveysPanel.tsx` | **yes, fully** | Mini App |
| Departments / "Команда ЭРА" / offices directory (`departments.py`, `directions_block7.py`) | ✅ keep, this is genuinely "связь с администрацией"-adjacent (who to contact) | partial — Mini App doesn't have a directory screen | no | Bot (it's a contact/lookup feature, not a data-entry one) |
| Questions to admin (`questions.py`) | ✅ keep — "связь с администрацией" | no equivalent, and doesn't need one | no | Bot |
| Achievements/badges display (`achievements_block4.py`) | fallback | ✅ Profile's achievements section | **yes, fully** | Mini App |
| `about.py` ("ℹ️ О боте") | ✅ keep, it's literally about the bot | n/a | no | Bot |

## Leader surfaces

| Feature | Bot | Mini App | Duplicate? | Primary UX |
|---|---|---|---|---|
| Leader panel menu tree (`leader/panel.py`, 758 lines) | fallback only | ✅ `LeaderScreen` (Overview/Open Tasks/Activities tabs, PR 9 + PR 32) | **yes, fully** | Mini App |
| Open task creation/management (`leader/open_tasks.py`) | fallback | ✅ `leader/OpenTasksTab.tsx` | **yes, fully** | Mini App |
| Event building (`leader/event_builder.py`, `leader/events_block6.py`) | fallback | project/event moderation lives in Admin Mode; leader-side event creation UX is a known Mini App gap | partial | Bot fallback until Mini App leader event-creation ships (tracked, not a launch blocker per owner's "not a real blocker → fix and continue" rule — flagged in PR 39) |
| Event Activities leader review (`leader/event_activities_block7.py`) | fallback + notification | ✅ `leader/ActivitiesTab.tsx` (PR 32) | **yes, fully** | Mini App |
| Task deadline reminders (`leader/task_deadline_buttons.py`) | ✅ keep — this *is* a notification | n/a | no | Bot |

## Admin surfaces

| Feature | Bot | Mini App | Duplicate? | Primary UX |
|---|---|---|---|---|
| `/admin` dashboard + full menu tree (`dashboard_block_a.py` → `panel.py`, `rights_block6.py`, `events_block6.py`, `projects_block5_decision.py`, `task_review_block2.py`, `auction_block17.py` admin half, `partner_offers_block16.py` admin half, `offices_management.py`, `analytics_filters.py`, `surveys_analytics.py`, `chat_binding_stability.py`, `partners_admin.py`, `approval_bonus_fix.py`) | **fallback/emergency only** — kept reachable via `/admin` and "⚙️ Управление" exactly as before, just no longer advertised on the default keyboard | ✅ `AdminScreen` (Dashboard, Applications, Projects, Events, Tasks, Offers, People, Offices, Surveys — PR 7–12, 29–32) | **yes, essentially the entire tree** | Mini App |
| Registration application review | fallback | ✅ `AdminApplicationsScreen` | yes | Mini App |
| Project moderation | fallback | ✅ `AdminProjectsScreen` / `ProjectModerationPanel` | yes | Mini App |
| Event moderation | fallback | ✅ `AdminEventsScreen` / `EventModerationPanel` | yes | Mini App |
| Task submission review | fallback | ✅ `AdminTasksScreen` | yes | Mini App |
| Offer/reward/auction application review | fallback | ✅ `AdminOffersScreen`'s panels | yes | Mini App |
| People / permissions / roles management | fallback | ✅ `admin/people/PeopleList.tsx` + `PersonDetail.tsx` | yes | Mini App |
| Offices management | fallback | ✅ `AdminOfficesScreen` | yes | Mini App |
| Analytics (incl. Excel export) | fallback | ✅ `AdminDashboardScreen` — on-screen metrics and Excel export both live here now (`downloadAnalyticsExcel`, `admin_analytics_service.py`) | yes | Mini App |
| Monthly goals / organization contacts / department structure / chat greetings (`management_ready.py`, `panel.py`'s `admin:greetings*`) | fallback | ✅ `AdminToolsScreen` (goals, contacts, structure, greetings sub-tabs — `admin_goals_service.py`, `admin_contacts_service.py`, `admin_structure_service.py`, `admin_greetings_service.py`) | yes | Mini App |
| General broadcast (personal DM + chat broadcast, 6-way audience targeting) | fallback | ✅ `AdminToolsScreen`'s Рассылки tab (`admin_broadcast_service.py`) | yes | Mini App |
| Chat binding via forwarded message | ✅ keep permanently — Telegram only exposes a chat's id through a message sent inside it, which a web form can't replicate | n/a | no | Bot |
| Test-data maintenance / wipe tool | fallback | ✅ `AdminMaintenanceScreen` (`maintenance_service.py`) — same ADMIN_IDS-only gate as the bot (`require_maintenance_access`, deliberately narrower than the general admin dependency) plus a real server-validated type-to-confirm phrase, not a UI-only confirm | yes | Mini App |
| Chat binding / general-chat administration (`chat_binding_stability.py`, `chat_binding.py`) | ✅ keep — "работу с общим чатом" | no equivalent needed | no | Bot |
| Emergency/maintenance commands (`emergency.py`, `management_ready.py`'s maintenance mode) | ✅ keep — explicit "резервный сценарий" requirement | n/a | no | Bot |

## What this means for PR 36 specifically

1. **`main_menu()`/`main_inline_keyboard()`** (`app/keyboards/participant.py`): replaced the old `👤 Личный кабинет / 📅 Афиша / ✅ Задачи / ⭐ Возможности / [🔥 Открыть ЭРА] / 💬 Связь / [⚙️ Панель]` tree with the brief's exact set — `🔥 Открыть ЭРА`, `📅 Ближайшее`, `✅ Мои задачи`, `⭐ Возможности`, `💬 Связь` — three of which now deep-link straight into the right Mini App tab instead of opening a bot-side inline menu. This only changes what's advertised when a Mini App URL is configured; the old buttons/handlers remain as the "Mini App unavailable" fallback (`else` branch, unchanged behavior, `⚙️ Панель` included for privileged/admin users in that branch specifically, satisfying "резервный сценарий, если Mini App временно недоступна").
2. **Frontend deep-linking** (`frontend/src/app/App.tsx`): extended the existing `#/projects/{id}` hash-parsing into a general `parseDeepLink()` that also recognizes `#/tasks`, `#/events`, `#/opportunities` — landing the user on the right tab (and right Activity sub-section) instead of always defaulting to Home.
3. **Not done in PR 36** (by design, per the owner's own "не удаляй сразу" instruction and PR grouping): no bot handler files were deleted, no admin panel restructuring, no per-notification deep-link rewiring (that's PR 40), no design-system work (PR 37), no Home/Profile/Portfolio content redesign (PR 38), no Leader/Admin Mini App UX polish (PR 39). This PR is scoped exactly to "stop the bot from *advertising* a second, competing interface" — the actual visual/product work the rest of the brief asks for follows in PR 37–42.
