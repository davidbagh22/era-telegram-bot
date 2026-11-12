# ЭРА — автономная разработка

Актуальная контрольная точка — [CODEX_HANDOFF.md](CODEX_HANDOFF.md).

## Состояние (обновлено: 2026-11-06)
- main SHA: 45622639484eea9babae748f50d90600600c9975 (#537 merged with expected HEAD 7e7347b) | последний подтверждённый Render LIVE: 4695807fad3dadd52826bfe5e839644b8d65d908.
- Запуск: в процессе, независимая задача исправления обновления базы знаний после изменения материала.
- #537: финальный HEAD 7e7347bd40281c71ebc8a2cfee052c3ced6efbe7 прошёл 6/6, включая PostgreSQL с 8 обработчиками; проверены source и отсутствие unresolved threads. Предыдущий main 4695807 прошёл 5/5 и был LIVE. Guarded merge выполнен. Новый main run 42202034867 ещё выполняется; автоматический deploy нового SHA пока не подтверждён.
- Политика повреждённых уведомлений: оставить записи неизменными, предупреждать по ключу; не преобразовывать string recipient IDs, не исправлять/удалять записи автоматически, не повторять uncertain/conflict. Ручная коррекция реальных записей требует отдельного разрешения.
- Проверки нового исправления: npm ci и npm run build (tsc + Vite) PASS, diff --check PASS. Локальный Playwright не запустил Chromium: socket() Operation not permitted; это ограничение среды, не успешный E2E. Полный E2E требуется в CI.
- Новое исправление: после успешного изменения материала старый список сразу инвалидируется; при ошибке повторной загрузки устаревшие карточки не показываются. Кнопка повторяет GET, а не PATCH. Добавлен браузерный regression test.
- Следующий шаг: завершить main 5/5 и автоматический LIVE #537, проверить health/ready и короткую выборку ошибок; затем финальные 6/6 нового PR базы знаний.
- #551: legacy NULL/missing-area и реальная ERA/KSOORS приёмка открыты; #542 резервный админ-доступ; #589 политика видимости; #605 исторические локальные даты. Не менять эти политики молча.
- Автозадача 6adcbd42ede08191a5c0a946e4147b52 содержит полное ТЗ; расписание сохранено.
- Нужно от владельца: пакетная реальная приёмка ролей и мобильных клиентов; CI и LIVE не равны ПРОВЕРЕНО.

## Реестр готовности (3/40 = 7,5%)

| ID | Requirement | Status | Remaining evidence / action |
|---|---|---|---|
| A01 | Registration and authorization full cycle | ВЫПУЩЕНО | Real fresh/resumed application, photo, approval and login |
| A02 | Roles and access boundaries | IN PROGRESS | Configured-admin guard and release evidence in [#542](https://github.com/davidbagh22/era-telegram-bot/pull/542). Real admin/leader/employee/participant matrix is BLOCKED: HUMAN ACCEPTANCE. |
| A03 | Convenient main menu | ВЫПУЩЕНО | Verify final mobile navigation and legacy keyboard |
| A04 | Remove «Мой путь» from profile | ВЫПУЩЕНО | Main ProfileScreen no longer renders «Мой путь»; real participant/mobile profile acceptance not confirmed |
| A05 | Buttons, typography and logo | В РАЗРАБОТКЕ | Mobile visual review against agreed design |
| A06 | iPhone and Android Mini App | В РАЗРАБОТКЕ | #620 iOS ICS calendar import, real Telegram iPhone/Android clients, not only Playwright |
| B01 | Event create/publish/edit | ВЫПУЩЕНО | #620 calendar export UX; real authorized scenario, no test announcement |
| B02 | Edit published event poster | В РАЗРАБОТКЕ | Wizard supports poster changes; published entry flow unconfirmed |
| B03 | Hide/remove events from general poster listing | В РАЗРАБОТКЕ | Draft #589 exists; high-risk visibility policy, PostgreSQL and human acceptance not confirmed; do not release |
| B04 | Publication latency and duplicate prevention | В РАЗРАБОТКЕ | #447 shipped; legacy #467/#491, uncertain receipts |
| B05 | Registration, waitlist, capacity and deadlines | IN PROGRESS | Capacity concurrency and release evidence in [#663](https://github.com/davidbagh22/era-telegram-bot/pull/663). #514/#510 policy parity, #507 notification ordering, and real Telegram acceptance remain. |
| B06 | QR attendance | ВЫПУЩЕНО | Real scoped confirmation and repeated-scan acceptance |
| B07 | Event points | ВЫПУЩЕНО | Actual attendance-to-ledger evidence, no test balance edits |
| B08 | Actual production event list | В РАЗРАБОТКЕ | Authenticated read unavailable; do not invent the list |
| C01 | Media chat and all eight topics | ПРОВЕРЕНО | 2026-11-02 LIVE b285de0: repeated 17:01/17:04/17:09 UTC 'Media forum ready: topics=8 navigation_message_id=8455'; setup_media_topics checks Telegram get_chat forum and bot admin topic/pin rights, 8 distinct ready thread IDs, reopen results and confirmed pinned navigation links. Does not claim each human member's private access. |
| C02 | Agreed media recruitment notification | ПРОВЕРЕНО | #429; Oct26 18:09:42Z sent message26588; receipt reuse, no resend |
| C03 | Media content plan and calendar | В РАЗРАБОТКЕ | #551 malformed metadata/scoped privacy; role acceptance |
| C04 | Media tasks and staff | В РАЗРАБОТКЕ | Complete assignment/review and scoped membership acceptance |
| C05 | Media materials and knowledge | ВЫПУЩЕНО | Knowledge base shipped; real upload/edit/access scenarios |
| C06 | Media notices, rights and damaged records | В РАЗРАБОТКЕ | #468 reminders; navigation rebinding receipt review |
| D01 | Simple manager assignments | ВЫПУЩЕНО | #488 three fields and /team_tasks; real user cycle |
| D02 | Complete/review/return tasks | ВЫПУЩЕНО | Different people, no self-review or double points |
| D03 | Task files, deadlines and reminders | В РАЗРАБОТКЕ | Real files and scoped 24h/3h delivery acceptance |
| D04 | Task statuses and manager notifications | ВЫПУЩЕНО | Actual acknowledgements and visibility by role |
| D05 | Pulse complete cycle and reports | В РАЗРАБОТКЕ | #446 concurrency fix shipped; real questionnaire/report |
| D06 | Repair leaders panel | В РАЗРАБОТКЕ | #520 shipped; actual existing panel repair unconfirmed |
| E01 | Points and duplicate award protection | ВЫПУЩЕНО | Full ledger/review/retry acceptance |
| E02 | Projects and portfolio | ВЫПУЩЕНО | Real lifecycle and privacy, upload/view/delete policy |
| E03 | Analytics from real data | ВЫПУЩЕНО | Verify period/scope totals against authorized source |
| E04 | Monthly projects PDF | ВЫПУЩЕНО | Layout tested historically; real complete month delivery |
| E05 | Games and team mechanics | В РАЗРАБОТКЕ | Content/round/result acceptance; Mafia excluded |
| E06 | Literature club | ВЫПУЩЕНО | Real issue, subscription, discussion and reporting |
| E07 | FAQ and support | ВЫПУЩЕНО | Scoped handling, replies and privacy acceptance |
| E08 | My Vector | В РАЗРАБОТКЕ | Methods/check-ins/goals/history/privacy and earlier backlog |
| E09 | Daily quotes | В РАЗРАБОТКЕ | Historical Nov 1–2 channel posts and Mini App quote API are evidenced, but future channel publications now require explicit approval for the exact text/day/target; approval UI and real authorized workflow are pending. No unapproved auto-posts permitted. |
| E10 | Broadcasts and notifications | В РАЗРАБОТКЕ | #491 incomplete receipts; no uncertain replay |
| E11 | Security and data protection | IN PROGRESS | Webhook release #662, configured-admin boundary #542, and remaining #484/#486 event privacy checks. |
| E12 | Backup and restore | ПРОВЕРЕНО | 2026-11-02 scheduled backup run 41407674271 SUCCESS: real production OIDC snapshot, isolated PostgreSQL 18 restore and migrations, encrypted/checksum round-trip, stored private artifact 13123694669 (expires 2026-11-09). External S3 copy optional and not configured; retention improvement remains advisable. |
| E13 | Legal/content organizational acceptance | В РАЗРАБОТКЕ | Draft #364 requires responsible human approval |
| E14 | Final multi-role production acceptance | НЕ НАЧАТО | All required scenarios, no known blockers, observation |

## Human blockers and non-negotiable constraints

- Authenticated Telegram/Mini App session and distinct real roles not available.
  Panel repair needs existing bot panel in the configured leaders topic and an
  authorized admin: /leaders_repair important as a reply, after verifying it.
  Do not manufacture panel receipts, messages, accounts or successful acceptance.
- PostgreSQL external allowlist is empty by design. Connector SQL cannot reach it;
  do not open it. Real event list needs an authorized application/secure internal read.
- Do not publish or resume «Траектория открытий», 31 October 2026, without new
  explicit user permission. Do not publish new ERA messages without concrete prior
  authorization. No mass tests or uncertain retries. No Mafia.
- No destructive migrations, deletion of user data or real points/participation
  changes for testing. No secrets in output. Respect dirty worktrees.
- Merge only reviewed exact HEAD with all required CI, then main CI and automatic
  Render checksPass. No manual deploy/bypass. CI/HTTP health != user acceptance.
- If a run hits platform limits, persist the next action and stop; never bypass
  limits. The next available hourly run continues here. No continuous execution
  between runs is promised.

## Журнал
- Текущий запуск: #537 — PostgreSQL regression probe, восемь обработчиков, malformed JSON/array/null/recipients/attempts; неизменность плохих записей, одна sent-транзакция для здоровой, ноль отправок. Добавлена защита от несовпадающего ключа/event_id/phase. CI ещё требуется.
- 2026-11-04: автозадача обновлена пользовательским ТЗ, расписание сохранено. main и Render LIVE совпадают: 4695807.
- 2026-11-02: #652 merged -> 4695807, автоматический Render LIVE подтверждён; новые реальные роли не проверялись.
- 2026-11-02: #523 merged -> 7ca1c75; EVENT_WIZARD_SYNC_EVENT_IDS остаётся default-empty. Включение реальных event IDs не разрешено этим выпуском.
- 2026-11-02: #651 календарь — durable safe_send_once, неизвестные результаты не повторяются; реальная iPhone-приёмка не подтверждена.
- 2026-11-02: #650 — активная регистрация требуется при начале и отправке activity proof.
- 2026-11-02: #648/#649 — точное согласование плановых публикаций, пользовательская приёмка workflow остаётся открытой.
- 2026-11-02: #646/#647 — согласование плановых публикаций и fail-closed при неизвестной доставке.
- Старые подробности доступны в git-истории этого файла; не перечитывать без конкретной причины.

## Отчётность
Один существенный суточный отчёт 09:00–19:00 Asia/Yerevan; вне окна только критический блокер. Последняя подтверждённая реальная приёмка: 3/40. CI и LIVE не равны приёмке. Не создавать отдельный PR только для отчёта.
