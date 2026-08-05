# ERA Platform — UI Design System (Mini App)

Единый источник правды по дизайн-токенам, примитивам и паттернам экранов
Mini App (`frontend/src`). Написан по факту кода на момент PR14, а не по
намерениям — если код и этот документ разойдутся, прав код, и это баг
документа.

## 1. Токены (`frontend/src/theme/tokens.css`)

Все цвета/радиусы/тени/шрифты — только через CSS-переменные `--era-*`,
никогда не через захардкоженный hex внутри компонента (кроме одного
осознанного исключения — см. раздел 4).

| Токен | Значение (light) | Назначение |
|---|---|---|
| `--era-red` / `--era-violet` / `--era-magenta` | `#e52b24` / `#742cc4` / `#be268f` | Основные брендовые акценты |
| `--era-gradient` | `linear-gradient(135deg, #742cc4 0%, #b529a6 48%, #e52b24 100%)` | Primary-кнопки, бейджи активных вкладок, шапки Admin/Leader режимов |
| `--era-bg` / `--era-surface` | фон страницы / фон карточек | |
| `--era-text` / `--era-text-muted` | основной / вторичный текст | |
| `--era-border` | разделители, обводки карточек/полей | |
| `--era-success` / `--era-warning` / `--era-error` | статусные цвета | Используются в `StatusBadge`, сообщениях об ошибках |
| `--era-radius-card` (20px) / `--era-radius-control` (0.875rem) | скругления карточек / кнопок-полей | |
| `--era-motion-fast` (0.15s) / `--era-motion` (0.25s) | длительности переходов | |
| `--era-font-display` (Unbounded) / `--era-font-body` (Golos Text) | заголовки / основной текст | |

### 1.1. Тёмная тема (добавлено в PR14)

Telegram передаёt `colorScheme`/`themeChanged` через `window.Telegram.WebApp`.
`telegram/webApp.ts::applyTelegramTheme()` пишет его в
`document.documentElement.dataset.theme`, а `tokens.css` переопределяет
`--era-bg/--era-surface/--era-text/--era-text-muted/--era-border/
--era-success/--era-warning/--era-error/--era-shadow-*` под
`:root[data-theme="dark"]`. Брендовые цвета (`--era-red/violet/magenta`,
`--era-gradient`) намеренно не меняются — они уже достаточно насыщены для
тёмного фона.

Вызывается дважды: синхронно в `main.tsx` (до первого рендера — без этого
был бы одно-кадровый "вспых" светлой темой в тёмном Telegram) и повторно в
`initTelegramWebApp()` (`useAuth.ts`), которая также подписывается на
`themeChanged`, чтобы тема менялась вживую, если пользователь переключит
тему Telegram прямо во время открытого Mini App.

До PR14 `getColorScheme()` существовал, но нигде не вызывался — тёмная
тема Telegram полностью игнорировалась (обычный баг несогласованности,
а не осознанное решение).

## 2. Общие примитивы (`frontend/src/components/`)

| Компонент | Когда использовать |
|---|---|
| `Card` | Контейнер контента с фоном/тенью/радиусом; `gradient` prop — для акцентных карточек (белый текст поверх `--era-gradient`) |
| `EmptyState` | Единственный способ показать "здесь пусто" или "не удалось загрузить" внутри списка/таба |
| `StatusBanner` | Полноэкранное сообщение о состоянии аккаунта (Pending/Blocked/AuthError) — не для списков |
| `StatusBadge` | Цветной статус-лейбл (заявка/задача/проект) |
| `MetricCard` | Числовая метрика в Home/Dashboard |
| `ProgressBar` | Прогресс уровня/выполнения |
| `PillTabs` | Переключатель вкладок внутри экрана (не путать с `BottomNavigation`) |
| `BottomNavigation` | Только нижняя навигация обычного участника (5 вкладок) |

## 3. Паттерн загрузки данных

Единственный принятый способ — хук `useAsync<T>(fetcher, deps)`
(`frontend/src/hooks/useAsync.ts`), возвращающий
`{status:"loading"} | {status:"ready", data} | {status:"error", detail}`.

Каждый экран, который читает данные с API, обязан отрисовать все три
состояния явно:

- `loading` → короткий текст «Загрузка…» (без спиннера — осознанно,
  единообразно, не требует доп. ассетов);
- `error` → `EmptyState`/`StatusBanner` с понятным русским текстом,
  никогда — пустой экран или необработанное исключение в консоли;
- `ready` + пустой массив → отдельный `EmptyState` с текстом "пока
  пусто", отличным от текста ошибки.

Проверено при аудите PR14: все 17 экранов/табов, использующих
`useAsync`, отрисовывают все три состояния (см.
`docs/PRODUCTION_READINESS_AUDIT.md` для истории — на момент PR13 это
было отмечено в бэклоге как непроверенное, PR14 закрывает эту проверку).

## 4. Осознанные исключения

- `Card.tsx`, `PillTabs.tsx`, `layouts/AdminLayout.tsx`,
  `screens/leader/OpenTasksTab.tsx`, `screens/projects/ProjectWorkspace.tsx`
  используют буквальный `#fff` для текста поверх `--era-gradient`/
  `--era-red` — это не отдельный "цвет", а константа "белый текст на
  насыщенном брендовом фоне", читается яснее токена и не нуждается в
  тёмной теме (тёмная тема не меняет сами брендовые фоны).
- До PR14 в `OpenTasksTab.tsx`/`ProfileScreen.tsx` были fallback-значения
  `var(--era-error, #E5342B)`, где резервный hex расходился с реальным
  токеном (`#d92d20`). Так как `tokens.css` подключается глобально и
  переменная всегда доступна, fallback был мёртвым кодом с неверным
  значением — убран, оставлен чистый `var(--era-error)`.

## 5. Safe area / мобильная корректность

`index.html` задаёт `viewport-fit=cover`, поэтому контент может уезжать
под чёлку/статус-бар/домашний индикатор устройства. Обязательные точки:

- `BottomNavigation` — `padding-bottom: calc(0.5rem + env(safe-area-inset-bottom, 0px))` (было до PR14);
- `UserLayout`/`AdminLayout`/`LeaderLayout` — `padding-top: env(safe-area-inset-top, 0px)` на корневом контейнере (добавлено в PR14 — отсутствовало для Admin/Leader и обычного User-layout);
- `StatusBanner` (Pending/Blocked/AuthError, рендерятся без layout-обёртки) — верхний паддинг увеличен на `env(safe-area-inset-top, 0px)` (добавлено в PR14).

## 6. Известные ограничения (не в этом блоке)

- Нет отдельного visual regression / Storybook — сверка "все экраны
  выглядят единообразно" делается вручную по этому документу и код-ревью,
  не автоматизирована.
- Спиннер/skeleton вместо текстового «Загрузка…» не введён — решение
  сознательно отложено, текущий вариант простой и уже единообразный
  везде, замена — чисто косметическое отдельное решение, не блокирующее
  production readiness.
