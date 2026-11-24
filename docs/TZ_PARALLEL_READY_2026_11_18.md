# ТЗ: параллельный дожим до «ПОЛНОСТЬЮ ГОТОВ»

Владелец 18.11.2026: не ждать один CI — вести несколько независимых потоков до упора в ожидание. Цель — бот/Mini App в статусе **ПОЛНОСТЬЮ ГОТОВ** по `docs/AUTONOMOUS_PROGRESS.md` максимально быстро.

## Операционный режим (обязательно)

1. **Никогда не простаивать на одном CI.** Пока `test`/`e2e` крутится — чинить другой FAIL, ребейзить следующий PR, писать точечные тесты, обновлять реестр.
2. **Параллельные workstream-агенты** (отдельные cloud VM / чаты), один владелец-координатор.
3. Merge только exact-head + полный CI + review; затем main CI → automatic Render LIVE → `/health`+`/ready`. Без ручного deploy.
4. Не трогать production данные, uncertain deliveries, секреты. Human acceptance (Telegram/роли) = BLOCKED, не выдумывать VERIFIED.
5. «ПОЛНОСТЬЮ ГОТОВ» запрещён, пока E14 и human blockers открыты — но всё кодовое/CI/LIVE доводится без паузы.

## Очередь merge (P0 — сейчас)

| PR | Тема | Правило |
|---|---|---|
| #690 | Portfolio visual v2 | Merge сразу после 6/6 на exact head → LIVE |
| #689 | Project covers contain | Merge сразу после 6/6 на exact head → LIVE |
| #675 | Home: прогресс ≠ Мой вектор | Safe UX; rebase на новый main после #690/#689 |
| #680 | Ranks + compact afisha | Safe UX; после #675 или независимо если нет конфликта |
| #674 | Full posters + typography | Safe UX |
| #676→#677→#679 | ERA 2.0 stack | Снизу вверх: base CI green → merge stack |
| Product waves 1–4 | theme/leaders/tests/admin-media | Stack merge после rebase на актуальный main |

## Очередь починки (P0 — параллельно ожиданию)

| PR | Проблема | Workstream |
|---|---|---|
| #484 | CI fail (test/migration/e2e) — poster security | WS-SEC |
| Stale drafts #589/#578/#665/#364 | Не мержить без явного owner OK | inventory only |
| #670 anniversary publish | High-risk broadcast — только с явного OK | inventory |

## Workstreams

### WS1 — Ship hotfixes (координатор)
- Держать подписки CI на #690/#689.
- Merge → main CI → LIVE SHA → health/ready.
- Обновить `CODEX_HANDOFF.md`.

### WS2 — UX safe merges
- #675, #680, #674: exact-head CI, конфликты с main, точечные тесты, PR ready.
- Не смешивать с security drafts.

### WS3 — ERA 2.0 + product waves stack
- Проверить stack parents/bases, rebase на main после WS1.
- Чинить CI по одному HEAD; не плодить дубликаты.

### WS4 — Security closeouts
- #484 (и связанный #486): починить CI, сохранить политику доступа, не ослаблять.
- После green — review + merge.

### WS5 — Ready matrix truth
- Пройти реестр A01–E14: фактический статус CODE COMPLETE / DEPLOYED / BLOCKED.
- Список human blockers одной страницей: что только владелец может закрыть (роли, Telegram, legal).

## Критерий «кодовый потолок» (до human acceptance)

- Все безопасные open PR либо в main+LIVE, либо закрыты как superseded/blocked с причиной.
- Нет красного CI на активных ship-ветках.
- LIVE SHA == main tip; `/health`+`/ready` ok.
- Реестр обновлён; E14 остаётся НЕ НАЧАТО/BLOCKED до реальной приёмки.

## Запреты

- Не ждать «статус?» — подписки сами.
- Не мержить draft high-risk visibility/broadcast без owner.
- Не объявлять «100% готово» без E14 + human acceptance.
