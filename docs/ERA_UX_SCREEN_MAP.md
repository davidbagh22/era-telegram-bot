# ERA Mini App — UX Screen Map

**2026-08 redesign, phase 6.** A flat inventory of every screen the Mini
App renders, how a user reaches it, and what deep-links into it — kept
next to `docs/UI_DESIGN_SYSTEM.md` (which documents the *how*: tokens,
components, the landing-menu/BottomSheet IA pattern) rather than
duplicating that reasoning here. This file documents the *what*: the
actual route/screen inventory as implemented, not an aspirational sitemap.

Update this file whenever a screen is added, removed, or moved between
tabs/groups — same "real, not aspirational" policy as the rest of `docs/`.

## URL scheme

The Mini App is a single-page app with no client-side router; the only
URL-addressable state is a one-time deep link parsed at mount by
`frontend/src/app/App.tsx`'s `parseDeepLink()`, reading
`window.location.hash`. Everything after that first render is local
`useState`, not reflected in the URL — see
`docs/UI_DESIGN_SYSTEM.md`'s "Information architecture" section.

| Hash | Lands on | Source |
|---|---|---|
| *(none)* | Главная (Home) | default |
| `#/tasks` or `#/tasks/{id}` | Активность → Задачи, optionally scrolled/highlighted to `{id}` | bot's "✅ Мои задачи" navigation-guide button, task notifications |
| `#/events` or `#/events/{id}` | Активность → Мероприятия, optionally highlighted | bot's "📅 Мероприятия" navigation-guide button, event notifications |
| `#/opportunities` or `#/opportunities/{id}` | Возможности → Предложения, optionally highlighted | bot's "⭐ Возможности" navigation-guide button, opportunity notifications |
| `#/profile` | Профиль | bot's "👤 Профиль" navigation-guide button |
| `#/projects/{id}` | Активность → Проекты → project detail | project-related notifications |
| `#/admin/projects/{id}` | Admin Mode → project detail (via `ProjectsScreen`, bypassing `AdminScreen`) | admin project notifications |

Built server-side by `app/utils/deep_links.py`'s `miniapp_*_url()`
helpers — the Mini App only ever parses this contract, it doesn't
generate it.

## Participant surfaces (`UserLayout`, 4 fixed bottom-nav tabs)

### 🏠 Главная — `HomeScreen.tsx`
Community-feed hero: avatar-in-progress-ring on a fixed gradient
"spotlight" background, "Сегодня" (next step / nearest event / active
task), "Моя активность" (points/projects/completed tasks/portfolio
count), "Возможности для вас" (1–3 recommended offers), one primary
button into Активность. No sub-navigation.

### 🗂 Активность — `ActivityScreen.tsx`
Landing menu (5 action cards), local `useState` section selector, no
tabs:

| Card | Screen | Notes |
|---|---|---|
| Проекты | `ProjectsSection.tsx` → `ProjectsList.tsx` / `ProjectDetail.tsx` | list has a "Фильтр" BottomSheet (Мои/Открытые/Предложения/Завершённые); detail always shows project content regardless of `can_edit`, with a separate "Редактировать" toggle and a "Рабочее пространство" toggle into `ProjectWorkspace.tsx` |
| Задачи | `activity/TasksTab.tsx` | open + assigned tasks |
| Мероприятия | `activity/EventsTab.tsx` | published events, register/cancel (cancel goes through a confirm `BottomSheet`) |
| Календарь | `activity/CalendarTab.tsx` | everything upcoming, by date |
| История | `activity/HistoryTab.tsx` | past events/tasks |

### ⭐ Возможности — `OpportunitiesScreen.tsx`
Landing menu (4 feature cards), same pattern as Активность:

| Card | Screen | Notes |
|---|---|---|
| Предложения | `OffersList` (in-file) | "Фильтр" BottomSheet (Для тебя/Все/Сохранённые/Мои заявки) |
| Аукционы | `opportunities/AuctionsPanel.tsx` | premium hero-card marketplace (PR 148); bid via detail `BottomSheet` |
| Каталог | `opportunities/RewardsPanel.tsx` | points-shop catalog, admin-reviewed redemption |
| Опросы | `opportunities/SurveysPanel.tsx` | one form per survey, all questions at once |

### 👤 Профиль — `ProfileScreen.tsx`
Avatar, growth-level progress bar, "Управление ЭРА" card (admin/leader
only, switches into their workspace), metric grid, "Рейтинг участников"
→ `LeaderboardScreen.tsx`, resume PDF download, portfolio sections
(Проекты/Мероприятия/Задачи/Волонтёрство/Лидерство/Достижения/
Сертификаты/Рекомендации), data export + account deletion request (own
"Данные и конфиденциальность" section). No sub-navigation beyond the
leaderboard push.

## Leader surface (`LeaderLayout`, entered via Profile's "Управление ЭРА")

### `LeaderScreen.tsx`
3-way `PillTabs` (short, fixed set — not the primary-navigation case the
2026-08 redesign retired `PillTabs` from): Обзор
(`leader/OverviewTab.tsx`) / Открытые задачи (`leader/OpenTasksTab.tsx`,
destination picked via a `BottomSheet`) / Активности
(`leader/ActivitiesTab.tsx`). "← Личное" in `LeaderLayout` returns to the
participant surfaces above.

## Admin surface (`AdminLayout`, entered via Profile's "Управление ЭРА")

### `AdminScreen.tsx` — 4 fixed bottom-dock groups (`AdminBottomNav.tsx`)

| Group | Sub-navigation | Screens |
|---|---|---|
| Обзор | none (landing) | `admin/AdminOverviewScreen.tsx` — "Требует внимания" action list, KPI grid, recent activity, collapsible "Полная аналитика и Excel-выгрузка" (`admin/AdminDashboardScreen.tsx`) and "Обслуживание" (`admin/AdminMaintenanceScreen.tsx`, ADMIN_IDS-gated) sections |
| Люди | `FilterChips` (4) | Участники (`AdminUsersScreen.tsx`) / Заявки (`AdminApplicationsScreen.tsx`) / Должности (`AdminOfficesScreen.tsx`) / Удаление данных (`AdminDataRightsScreen.tsx`) |
| Работа | `FilterChips` (4) | Проекты (`AdminProjectsScreen.tsx` → `ProjectModerationPanel.tsx`, list → detail → decision `BottomSheet`) / Мероприятия (`AdminEventsScreen.tsx`) / Задания (`AdminTasksScreen.tsx`) / Возможности (`AdminOffersScreen.tsx`) |
| Коммуникации | `FilterChips` (2) | Опросы (`AdminSurveysScreen.tsx`) / Инструменты (`AdminToolsScreen.tsx` — goals, contacts, structure, greetings, broadcast, chat registry, maintenance) |

"← Личное" in `AdminLayout` returns to the participant surfaces above.
`#/admin/projects/{id}` bypasses this grouping entirely and opens
`ProjectsScreen.tsx` directly (admin-context project detail).

## Bot-side surfaces (not the Mini App, but part of the same navigation contract)

- **`main_inline_keyboard()`** — the bot's one persistent menu, sent on
  `/start`, registration/role-change approvals, and anywhere a
  "← Главное меню" back-button used to live. When a Mini App URL is
  configured (always in production): 🔥 Открыть ЭРА (opens the app at
  Home) / 🧭 Навигация (see below) / 💬 Связь (bot-native contact menu —
  the one flow deliberately kept bot-side, since a question-to-admin
  conversation doesn't need to be inside the Mini App). Fallback (no
  Mini App URL, e.g. local dev): the old 👤 Личный кабинет/📅 Афиша/✅
  Задачи/⚙️ Панель bot-native tree.
- **🧭 Навигация** (`nav_guide_callback`) — a role-aware bot message
  (participant/leader/admin) explaining what's in each part of the app,
  with `navigation_guide_keyboard()`'s deep links (📅 Мероприятия / ✅
  Задачи / ⭐ Возможности / 👤 Профиль, plus a workspace button for
  leaders/admins). The bot explains and links; it never re-implements a
  screen's content.
- **Legacy `/panel`, `/admin` bot-native handler tree** — kept
  unadvertised as an emergency fallback (`archive/legacy_bot/`-adjacent
  live code, not deleted — see `docs/BOT_VS_MINIAPP_AUDIT.md`), reachable
  only by typing the command directly, not from any button.
