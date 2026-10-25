# ERA Mini App — UI Design System

**PR 37.** This documents what's actually implemented in
`frontend/src/theme/tokens.css` and `frontend/src/components/` — not an
aspirational spec sitting next to the code. Every token and component
below is real, imported, and used somewhere in the app today. When PR 38
and PR 39 redesign the remaining screen content, they extend this system
rather than inventing new one-off styles — that's the whole point of
having it.

## Redesign (2026-08) — complete

The project owner handed down a full 52-section product/UX/UI redesign
brief (private, not committed to the repo verbatim — this doc absorbs the
concrete tokens/rules from it as they're actually implemented, same
"real, not aspirational" policy as everything else here). It was
executed as 6 phases, each its own PR:

1. **Foundation** — dark-first palette tokens, exact brand gradient
   stops, hero typography step, added to the existing opt-in
   `:root[data-theme="dark"]` block. `:root` (light theme) was
   deliberately **not** flipped to dark-first — that's its own decision
   with app-wide visual blast radius, left for a future call rather than
   bundled into this redesign.
2. Critical project-detail bug fix — `ProjectDetail.tsx` now always
   renders the project's content regardless of `can_edit`, with a
   separate "Редактировать" toggle instead of the old "Форма/Workspace"
   split; `AdminProjectModerationPanel` restructured to list → detail →
   `BottomSheet` decision instead of 5 stacked buttons under a raw status
   pill.
3. **Navigation/IA restructure** — see "Information architecture" below
   for the pattern this landed: `BottomNavigation` down to 4 fixed
   destinations (Главная/Активность/Возможности/Профиль), "Проекты"
   folded into Активность as an action card rather than its own tab.
4. **Screen-by-screen redesign** — `OpportunitiesScreen` rebuilt on the
   same landing-menu pattern (Предложения/Аукционы/Каталог/Опросы);
   Admin Mode's bottom dock down from 5 groups to 4
   (Обзор/Люди/Работа/Коммуникации), Аналитика folded into Обзор as a
   collapsible section. Home/Auction/Profile were already reasonably
   aligned with the brief from earlier PRs (PR 37's hero card, PR 148's
   auction marketplace redesign) and didn't need further screen-level
   restructuring in this pass.
5. **Bot navigation button + role-aware nav card** — the bot's
   advertised menu (`main_inline_keyboard()`) is exactly 🔥 Открыть ЭРА
   / 🧭 Навигация / 💬 Связь; the old 3 separate quick-access WebApp
   buttons collapsed into one 🧭 Навигация callback that opens a
   role-aware explainer message (participant/leader/admin) with the
   same deep links, so the bot explains and links to the app instead of
   carrying a second, parallel navigation surface.
6. **Final screen-map doc + manual QA pass** (this section) —
   `docs/ERA_UX_SCREEN_MAP.md` created; see that file for the full
   route/screen inventory and the manual QA walkthrough result.

## Information architecture

The pattern established across phases 3–4, used consistently instead of
horizontal tabs wherever a screen has genuinely different views (not
just a filter on one list):

- **Landing menu → detail, via local `useState`, not a router.** A
  screen with sub-sections (`ActivityScreen`, `OpportunitiesScreen`,
  `AdminProjectModerationPanel`) renders a list of `Card`s (icon in a
  gradient square, label, description, `→`) when nothing is selected;
  tapping one sets local state to that section/item and shows it with a
  `← Parent` back button and a section-specific `<h1>`. No client-side
  router, no URL change on this navigation — only the top-level deep
  link (`#/tasks`, `#/projects/{id}`, etc.) is parsed once at mount
  (`App.tsx`'s `parseDeepLink()`).
- **`BottomSheet` scope picker for same-shape list filters.** When the
  options genuinely just filter one list into different subsets of the
  same shape (`ProjectsList`'s Мои/Открытые/Предложения/Завершённые,
  `OffersList`'s Для тебя/Все/Сохранённые/Мои заявки), a single
  "Фильтр" button opens a `BottomSheet` with a vertical radio-style
  list, rather than a horizontal `PillTabs`/`SegmentedTabs` row.
- **`PillTabs`/`SegmentedTabs` are demoted, not gone.** They remain in
  the codebase for cases that are neither of the above — a fixed, short
  (2–4 option) admin sub-navigation within an already-selected group
  (`FilterChips` in `AdminScreen.tsx`'s People/Work/Comms groups) — but
  are no longer used as a screen's *primary* navigation anywhere a
  landing-menu or BottomSheet pattern fits instead.
- **4 fixed bottom-nav destinations for participants**
  (`BottomNavigation.tsx`): Главная / Активность / Возможности /
  Профиль. **4 fixed groups for Admin Mode** (`AdminBottomNav.tsx`):
  Обзор / Люди / Работа / Коммуникации.

### New brand tokens (phase 1)

| Token | Value | Use |
|---|---|---|
| `--era-black` | `#0B0910` | dark-theme page background |
| `--era-plum` | `#15101C` | dark-theme card/sheet surface |
| `--era-surface-dark` | `#1D1625` | dark-theme raised surface (`--era-surface-2`) |
| `--era-gold` | `#F5B942` | achievements/streaks/auctions only, see existing note below |
| `--era-text-4xl` | `2rem` (32px) | hero H1 (Home greeting) — the top of the brief's 28–32px H1 range |

`--era-gradient`'s middle stop changed from an intermediate blended hue
(`#b529a6`) to `--era-magenta` itself (`#be268f`) — the brief specifies
the gradient as exactly violet → magenta → red, not violet → *a* pink →
red.

## Brand direction

ЭРА's own words: energy, movement, growth, a youth environment,
modern, a light touch of elitism, technological. Concretely, that means:

- **The gradient is the hero, used sparingly.** `--era-gradient` (violet
  → magenta → red) appears on primary actions and one "spotlight" card
  per screen (`<Card gradient>` — Home's "next step"), never as a
  background wash or on more than one element at a time. That's what
  keeps it feeling like an accent, not decoration.
- **Everything else is quiet.** Flat white/near-black surfaces, one
  border color, two shadow levels. No decorative gradients elsewhere, no
  drop-shadow-everything "MVP dashboard" look.
- **Typography carries the energy instead.** `Unbounded` (display,
  geometric, confident) for headings and hero numbers; `Golos Text`
  (body) for everything you actually read. The contrast between the two
  is doing more of the "modern/youthful" work than color ever should.

## Tokens (`frontend/src/theme/tokens.css`)

### Color

| Token | Light | Dark | Use |
|---|---|---|---|
| `--era-red` / `--era-violet` / `--era-magenta` | fixed, same in both themes | — | brand accents, never surfaces |
| `--era-gradient` | `linear-gradient(135deg, violet → magenta → red)` | — | primary buttons, spotlight cards |
| `--era-bg` | `#f8f6f9` | `#0b0910` (`--era-black`) | page background |
| `--era-bg-subtle` | `#ffffff` | `#08060c` | recessed surfaces (inputs) |
| `--era-surface` | `#ffffff` | `#15101c` (`--era-plum`) | cards, sheets, modals |
| `--era-surface-2` | `#f4eefa` | `#1d1625` (`--era-surface-dark`) | raised surfaces above `--era-surface` |
| `--era-text` / `--era-text-muted` | — | — | primary / secondary text |
| `--era-border` | `#eae5ed` | `#362c40` | the one border color in the app |
| `--era-success` / `--era-warning` / `--era-error` | — | — | status semantics (StatusBadge, toasts) |

Dark mode is driven by `:root[data-theme="dark"]`, set by
`telegram/webApp.ts`'s `applyTelegramTheme()` mirroring Telegram's own
`colorScheme` (kept live via the `themeChanged` event) — the Mini App
never has its own light/dark toggle, it always matches the host app.
Brand colors (`--era-red`/`--era-violet`/`--era-magenta`,
`--era-gradient`) deliberately don't change between themes — they're
already saturated enough to read on a dark surface. Called twice:
synchronously in `main.tsx` before the first render (otherwise there's a
one-frame flash of the light theme in dark Telegram), and again from
`initTelegramWebApp()` (`useAuth.ts`), which also subscribes to
`themeChanged` so the theme updates live if the user switches Telegram's
own theme while the Mini App is open.

### Typography scale

`--era-text-xs` (0.75rem) through `--era-text-3xl` (1.75rem) — see the
table in `tokens.css` for exact use per step. `--era-font-display`
(Unbounded) is for headings/hero numbers only; `--era-font-body` (Golos
Text) is everything else, including buttons and inputs.

This codebase's established pattern (PR 14's design audit) is React
inline `style` objects, not utility classes — the scale isn't
auto-applied by a CSS cascade the way Tailwind's would be. Every inline
`fontSize` a screen sets should still be drawn from this scale rather
than an arbitrary number; the scale's job is to be the single source of
truth for "what sizes exist," not to enforce itself mechanically.

### Spacing scale

`--era-space-1` (0.25rem) through `--era-space-8` (2rem), 4px base unit —
matches the rem values already used ad hoc across every screen's
`gap`/`padding`/`margin`.

### Radius

- `--era-radius-sm` (0.625rem) — small chips, skeleton blocks
- `--era-radius-control` (0.875rem) — buttons, inputs
- `--era-radius-card` (20px) — cards, modals
- `--era-radius-pill` (999px) — pill tabs, status badges, drag handles
- `--era-radius-sheet` (1.5rem) — bottom sheet top corners only

### Shadow & motion

- `--era-shadow-soft` — resting card elevation
- `--era-shadow-lift` — hover/active card elevation, modal elevation
- `--era-shadow-overlay` — upward shadow for bottom sheets
- `--era-motion-fast` (0.15s) — taps, hovers, overlay fade-in
- `--era-motion` (0.25s) — page transitions, sheet slide-in

## Components (`frontend/src/components/`)

### Existing (pre-PR 37, unchanged)

- **`Card`** — the base surface. `gradient` prop for the one
  spotlight-per-screen case.
- **`MetricCard`** — a single stat (label + big number).
- **`ProgressBar`** — the growth-level stepper (Участник → Активный →
  Лидер).
- **`StatusBadge`** — small colored pill for a status word.
- **`StatusBanner`** — full-screen **error state**: centered icon-less
  title + description + optional retry action. Used by every screen's
  `useAsync` error branch. This *is* the app's error-state component —
  PR 37 didn't add a separate one because this already covers it well.
- **`EmptyState`** — the app's **empty state**: a single centered line of
  muted text, used when a list/query legitimately has zero results (not
  the same as an error — `useAsync`'s "error" and "ready with []" are
  rendered differently everywhere, on purpose).
- **`PillTabs`** — a scrollable pill-track filter control. Since the
  2026-08 redesign (see "Information architecture" above) no longer the
  app's primary navigation anywhere a landing-menu or `BottomSheet`
  scope picker fits instead — used today for short, fixed
  sub-navigation within an already-chosen area.
- **`BottomNavigation`** — the app's primary **navigation**: 4 fixed
  destinations (Главная/Активность/Возможности/Профиль), `TabKey`-driven.
- **`icons.tsx`** — the small inline-SVG icon set used by
  BottomNavigation and a few cards.

### New in PR 37

- **`Avatar`** — initials on the brand gradient, 3 sizes (`sm`/`md`/`lg`).
  ERA doesn't have a profile-photo pipeline into the Mini App API (see
  `docs/BOT_VS_MINIAPP_AUDIT.md`), so this is a deliberate, permanent
  design choice, not a placeholder for photos "coming later." Used in
  `HomeScreen`'s greeting and `ProfileScreen`'s header.
- **`Skeleton` / `SkeletonText` / `SkeletonCard` / `SkeletonList`** — the
  app's **loading state** primitive, replacing the plain "Загрузка…"
  text every screen used to render on its own. `Skeleton` is a single
  shimmering block (`era-shimmer` keyframe in `tokens.css`); the other
  three are compositions shaped like real content (a paragraph, a Card,
  a list of Cards) so the layout doesn't visibly jump once real data
  arrives. Wired into `HomeScreen`, `ProfileScreen`, `EventsTab`,
  `TasksTab` in this PR; the remaining screens pick it up naturally as
  PR 38/39 touch their content.
- **`Modal`** — centered dialog with a backdrop, closes on backdrop
  click or Escape. For content that genuinely wants to be centered
  (first-load informational dialogs) rather than reached-for with a
  thumb.
- **`BottomSheet`** — slides up from the bottom, same backdrop mechanics
  as `Modal`. This is the **primary** overlay for a touch-only app (see
  `frontend/e2e/*.spec.ts`'s fixed mobile viewport) — prefer it over
  `Modal` for anything attached to a card's own action (confirmations,
  quick pickers, short in-context forms). First real usage: `EventsTab`'s
  "Планы изменились" (cancel registration) now opens a confirm sheet
  instead of cancelling on a single tap — a real UX fix (no destructive
  action in the app previously had a confirmation step), not just a
  design-system demo.
- **`Toast` (`ToastProvider` / `useToast()`)** — top-of-screen, 3.5s
  auto-dismissing notifications with a success/error/info tone (colored
  left border). Mounted once at the app root (`main.tsx`). This codebase
  never used a native `alert()`/`confirm()` (a WebView `alert()` blocks
  and looks foreign inside Telegram) — `useToast()` is the replacement
  pattern for "tell the user something happened" that isn't already
  covered by a refetched list or a `StatusBanner`. First real usages:
  `ProfileScreen`'s resume download (success/error), `EventsTab`'s
  register/cancel actions.

## Loading / error / empty discipline

The one accepted way to read data is `useAsync<T>(fetcher, deps)`
(`frontend/src/hooks/useAsync.ts`), returning `{status:"loading"} |
{status:"ready", data} | {status:"error", detail}`. Every screen that
reads from the API is expected to render all three states explicitly —
verified across all `useAsync` call sites in PR 14's audit, extended to
cover `Skeleton` in PR 37:

- `loading` → `Skeleton`/`SkeletonList` (was plain "Загрузка…" text
  before PR 37 — deliberately deferred then as "purely cosmetic, not a
  production-readiness blocker," closed now).
- `error` → `EmptyState` (panel-level) or `StatusBanner` (whole-screen),
  never a blank screen or an unhandled exception in the console.
- `ready` + empty array → its own `EmptyState`, textually distinct from
  the error message.

## Deliberate exceptions

- `Card.tsx`, `PillTabs.tsx`, `layouts/AdminLayout.tsx`,
  `screens/leader/OpenTasksTab.tsx`, `screens/projects/ProjectWorkspace.tsx`
  use a literal `#fff` for text over `--era-gradient`/`--era-red` — not a
  separate "color," but the constant "white text on a saturated brand
  background," which reads more clearly than a token would and doesn't
  need a dark-theme variant (dark mode doesn't change the brand
  backgrounds themselves).
- Before PR 14, `OpenTasksTab.tsx`/`ProfileScreen.tsx` had
  `var(--era-error, #E5342B)`-style fallback values whose hex had drifted
  from the real token (`#d92d20`). Since `tokens.css` is loaded globally
  and the variable is always available, the fallback was dead code with
  a wrong value — removed, left as plain `var(--era-error)`.

## Safe area

`index.html` sets `viewport-fit=cover`, so content can slide under a
device's notch/status bar/home indicator. Required checkpoints:
`BottomNavigation`'s `padding-bottom: calc(0.5rem +
env(safe-area-inset-bottom, 0px))`; every layout
(`UserLayout`/`AdminLayout`/`LeaderLayout`)'s root
`padding-top: env(safe-area-inset-top, 0px)`; `StatusBanner` (renders
outside any layout for Pending/Blocked/AuthError) has its own top padding
increased by the same inset.

## When to reach for what

| Situation | Component |
|---|---|
| A list/query legitimately has zero results | `EmptyState` |
| A fetch failed and the whole screen can't render | `StatusBanner` |
| A fetch failed for one small panel inside an otherwise-working screen | inline muted/error text (see `EventActivitiesPanel` in `EventsTab.tsx`) — not every failure needs a full-screen treatment |
| Data is still loading | `Skeleton`/`SkeletonList` (not plain text) |
| Confirming a destructive or consequential action reached for with a thumb | `BottomSheet` |
| A centered, non-thumb-reached dialog | `Modal` |
| "Your action succeeded/failed" that isn't already obvious from the UI updating | `useToast()` |
| Showing a person | `Avatar` |

## Explicitly not building

- **A photo-based Avatar.** No backend support, no product need stated
  in the brief beyond "покажи фото" for Profile — initials-on-gradient
  already reads as a real product decision (see Slack, Linear, many
  others), not a placeholder.
- **A generic `<Table>` primitive.** The brief is explicit: "Никаких
  огромных технических таблиц по умолчанию" for Admin Mode — lists in
  this app are card-based, and that's staying true everywhere, not just
  in Admin.
- **A component library documentation site (Storybook, etc.).** This
  file plus the components' own doc comments is the documentation; a
  separate rendering tool is more infrastructure than a ~45-screen app
  built by one team needs right now.
