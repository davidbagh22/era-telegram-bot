# ТЗ ЭРА — довести бота и Mini App до «ПОЛНОСТЬЮ ГОТОВ»
Утверждено владельцем 15.11.2026. Работать по этому ТЗ и существующему реестру, без нового параллельного проекта.

## Результат и критерий остановки
Статус «ПОЛНОСТЬЮ ГОТОВ» разрешён только когда каждый согласованный сценарий реализован, выпущен и подтверждён проверкой, а открытых блокеров готовности нет. Закрытие старого PR, успешный CI и HTTP 200 сами по себе не являются приёмкой функции. При блокере фиксировать точную причину и продолжать независимую безопасную работу. Не обещать непрерывную работу между запусками; существующая почасовая задача продолжает с этой контрольной точки.

## Объём
1. Регистрация и возобновление заявки, согласование, авторизация, роли и приватность.
2. Мероприятия: создание/редактирование/фото/видимость, публикация, запись, вместимость, очередь, отмена, QR, посещаемость и однократные баллы.
3. Mini App: русские тексты, понятное меню, задачи на главном экране, аккуратное портфолио, PDF в чат; iPhone/Android, пустые состояния и ошибки.
4. Задачи/проверка/возврат/файлы/сроки, медиа и восемь тем, календарь, материалы, панель руководителей, Пульс и Мой вектор.
5. Аналитика по реальным данным, сертификаты, проекты, FAQ, игры без мафии, литературный клуб, согласованные цитаты и рассылки.
6. Согласованные ранее годовщина/гостевая запись/напоминания (#669), интеграция Google Calendar (#664) и экспертная платформа (#616). Не считать частичный payload-builder законченной интеграцией.
7. PostgreSQL, Redis, планировщик, очередь доставки, резервное копирование и изолированное восстановление. Очистка только доказанно ненужного кода/воспроизводимого мусора.

## Порядок выполнения
- Сначала блокирующий CI и P0 безопасности/потери/дублирования данных, затем готовые безопасные PR, надёжность очередей, основные функции, интерфейс и оставшиеся согласованные интеграции.
- Для каждого блока: текущий main/PR/блокировки → минимальное исправление → точечный тест → commit/push в существующий PR → полный CI на точном HEAD → review → merge с expected SHA → CI main → автоматический Render LIVE того же SHA → health/ready/связанные сценарии.
- Во время CI выполнять независимую задачу. Конфликт разрешать с сохранением актуального main, истории и чужих изменений. Не создавать повторных реализаций и PR для одного отчёта.
- Каждому требованию присвоить один статус: NOT STARTED / IN PROGRESS / CODE COMPLETE / DEPLOYED / VERIFIED / BLOCKED. Хранить ссылку на тест/PR/SHA/фактическое подтверждение и следующую конкретную задачу.
- Существующий реестр и согласованные дополнительные эпики — единый объём приёмки; не выдавать старые проценты за текущую готовность.

## Проверка перед финальным статусом
- Все обязательные CI успешны, активный production соответствует проверенному main.
- Пройдены сценарии участника, руководителя и администратора, включая отказ в чужом доступе, повторный запрос/QR, закрытую запись, ожидание/отмену, повторный callback и сбой сети.
- Подтверждены реальные Telegram и мобильные сценарии разрешёнными действиями; тестовые аккаунты, баллы, регистрации и рассылки в production не создавать.
- Нет необработанных исключений в ограниченной выборке журналов; затем подтверждено согласованное окно наблюдения. Планировщик и хранилища доступны, восстановление резервной копии проверено отдельно.
- Для неопределённых доставок есть безопасный статус и понятное ручное разбирательство; автоматической повторной отправки нет.
- Все зависимости от согласий, реальных ролей, учётных записей внешних сервисов и правовой приёмки явно закрыты. Если доступ недоступен — BLOCKED, не VERIFIED.

## Неизменные ограничения
Не удалять реальные данные, очереди, retry/dead-letter, баллы, роли, регистрации и историю. Не менять секреты, критические настройки, защиту веток; не обходить CI/review. Не повторять uncertain-доставки. Публиковать только конкретно согласованные материалы; запрет на повторную публикацию «Траектории открытий» 31.10.2026 сохраняется. Не включать мафию. Не подменять документы/согласия/доказательства вымышленными.

## Контрольная точка и отчёт
Этот файл + существующая почасовая задача 6adcbd42ede08191a5c0a946e4147b52. После результата сохранять текущий SHA, PR, тесты, LIVE, блокер и следующий шаг. Итог до 10 строк: что исправлено/выпущено/проверено, что осталось и точное продолжение. «ПОЛНОСТЬЮ ГОТОВ» — только после выполнения всех критериев выше.

## Продолжение 17.11.2026
- Готово в main: ranks/afisha UX, product waves 1–4, certs/media, portfolio PDFs, project covers, portfolio visual v2.
- ERA 2.0 stack CODE COMPLETE on tip: #676 UX + #677 auto-archive/media/certs + #679 welcome chats + PRO/RU cleanup — restacked onto latest main.
- Блокеры: Telegram acceptance (E14); need CI after force-push.
- Следующая: CI green → merge #679 (includes downstack) → LIVE verify.

## Продолжение 16.11.2026
- C06: уточнён текст на включительных границах 24 и 3 часа. Существующий 3h opt-in сохранён. Приёмка доставки в реальном media-чате открыта.
- Базовый main и Render LIVE: ab0c628, Bot checks [43764677578](https://github.com/davidbagh22/era-telegram-bot/actions/runs/43764677578), production smoke [43913145798](https://github.com/davidbagh22/era-telegram-bot/actions/runs/43913145798) успешны.

- #672: исправление текста C06 выпущено, CI PR 6/6, main 5/5, Render LIVE 42a3cd0, /health и /ready 200.
- E11 / #484: публичная афиша использует явный allowlist статусов и общий fail-closed MIME-фильтр; DRAFT/PENDING/CANCELLED/unknown остаются 404 (согласовано с #486). Следом CI и ревью точного HEAD #484.

## Продолжение 15.11.2026
- #500 merged after exact 6/6 and independent review -> main 30edfeb2b91df72d8789b339f4ea07a66d31ed51. Main CI / automatic LIVE pending.
- #491 source + all six CI passed on bcb4e67; independent review clean. Reconciled progress conflict with #500; require new-head CI. Four extracted accounting cases and syntax compile PASS.
- Real Telegram acceptance blocked: native app displays QR login, no authenticated session. No real users/messages/registrations changed.

## CI repair — 2026-11-15 22:52 Asia/Yerevan
- Full CI found an unrelated aiogram compatibility failure: test_group_commands_accept_bot_mention mock lacks Bot.usernames(). Add empty async usernames to preserve foreign-bot rejection. No production command filter changed. #653 run 43747336912: 2606 passed, one fixture failure; all other jobs passed. Apply the same fixture repair on #500/#653; exact-head full CI must rerun. Main #605 automatic rollout remains gated.

## FAST CLEANUP — 2026-11-15 (run cleanup-500-653-20261115)
- Closed 34 obsolete checkpoint-only PRs and duplicate #661; branches/commits retained. #580 kept because it contains a separate reconciliation procedure.
- #605 reviewed at 8f890855, all 6 checks successful, merged with expected SHA -> main 72c9ccfbd69611334d780c2d44ed7e97281ed4ee. Owner UTC decision is recorded in PR description. Main CI and automatic LIVE verification pending.
- Last confirmed Render LIVE: 747b33b2685b5a7c24ec573eaa58e9f241f88ef2. Scheduled smoke 43730856640 PASS including health/ready. PostgreSQL and persistent Redis available, scheduler jobs successful; ERROR sample 17:30–18:32 UTC empty. Old free Redis suspended; do not delete.
- #653 conflict resolved against main; malformed GitHub check collections now produce UNVERIFIED instead of crashing. Commit 40e9468095b98e8002876deea2a72b95370438b0; local 2 tests / 8 malformed inputs PASS; CI in progress. Schedule integration and independent review remain.
- #500 reconciled with current main: malformed reminder configuration skipped as a whole, never salvaged into partial sends. Valid integer thresholds retain semantics; no arbitrary one-year cap. Reject values exceeding PostgreSQL receipt Integer. Existing delivery keys/receipts untouched. Isolated extracted parser: 6 unittest tests PASS; full app CI pending.
- Remaining PR blockers: #670/#660/#578/#589/#491/#486/#484/#468/#467 conflict with main and have delivery/privacy/acceptance gates; #665 is only a payload builder, missing authorized Calendar adapter/outbox; #364 legal acceptance; #580 historical reconciliation procedure review.
- Existing enabled hourly automation 6adcbd42ede08191a5c0a946e4147b52 retained, no duplicate. Local dirty workflow edits preserved. No production data, queues, secrets or settings changed.
- Next: finish exact-head CI/review #500 and #653, confirm #605 main CI + automatic exact LIVE, then guarded release of safe fixes. Telegram/mobile role acceptance still unverified.

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
| B05 | Registration, waitlist, capacity and deadlines | IN PROGRESS | Capacity #663, commit-before-notice #507, and policy parity #514 are deployed. Durable recovery #497 and its release evidence are in [#666](https://github.com/davidbagh22/era-telegram-bot/pull/666). Waitlist scoring #513 and real Telegram acceptance remain. |
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
| E11 | Security and data protection | IN PROGRESS | Webhook #662 + admin boundary #542 + #691 CANCELLED detail/poster privacy shipped; follow-up `cursor/security-ecc-hardening-bd19` closes register/cancel/activities existence oracles. Anniversary/referral/portfolio downloads reviewed OK. |
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

## Owner addition — anniversary RSVP (2026-11-13)
- New mandatory requirement F01: direct bot guest registration for 12 December 2026, 17:30, cinema hall, name/surname/organization and private organizer list. IN PROGRESS; branch feat/anniversary-2026-rsvp.
- Register denominator is now 41; prior evidenced acceptance remains 3/41 (7.3%). F01 needs exact production deployment and real guest/admin acceptance before VERIFIED.
