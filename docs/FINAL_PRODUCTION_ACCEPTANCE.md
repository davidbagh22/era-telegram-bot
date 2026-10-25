# ERA PLATFORM — FINAL PRODUCTION ACCEPTANCE

Дата ревизии: 2026-08-14

## Вердикт

**CODE COMPLETE / PRODUCTION CONFIGURATION REQUIRED**

Оставшиеся пункты master-spec, которые можно закрыть изменением репозитория, реализованы в PR #201. Платформа не должна называться полностью `production-ready`, пока не выполнены внешние owner actions из последнего раздела и не подтверждён первый реальный внешний backup + restore.

Наличие кода health/backup/security не считается доказательством, что GitHub, Render и внешнее object storage уже настроены.

## 1. Phase 7 / единый интерфейс

Закрыто:

- `AdminToolsScreen` больше не использует `PillTabs` как навигацию;
- внутренние admin tools открываются через action rows/screens с явным Back;
- сохраняются четыре фиксированные группы Admin Mode — «Система» не создаёт пятую нижнюю вкладку;
- ключевая participant navigation переведена на hash-state;
- поддерживаются маршруты `#/home`, `#/projects`, `#/projects/:id`, `#/tasks`, `#/tasks/:id`, `#/calendar`, `#/history`, `#/events`, `#/events/:id`, `#/community`, `#/opportunities`, `#/opportunities/:id`, `#/auctions`, `#/rewards`, `#/surveys`, `#/leaderboard`, `#/profile`;
- `hashchange`/`popstate` синхронизированы с UI;
- browser/Telegram Back больше не зависит только от первоначального React state;
- E2E дополнен маршрутами Community и возвратом через browser history.

## 2. Legacy Bot UI

- Legacy `app/handlers/admin/panel.py` больше не регистрируется в production admin router.
- Старые compatibility-команды могут оставаться redirect/reference-слоем, но старая admin browse-tree не является production surface.
- Bot остаётся gateway/notification/quick-action слоем; Admin/Leader workspace находится в Mini App.

## 3. Runtime System / Health

Добавлены persisted-модели:

- `SystemDiagnosticRun`;
- `SystemIncident`;
- `BackupHistory`.

Alembic: `0018_system_health`, parent `0017_task_deliveries`. Migration additive-only и не переписывает существующие пользовательские/product tables.

Автоматические jobs подключены к реальному FastAPI/webhook production process и optional polling entrypoint:

- heartbeat — каждые 15 минут;
- full diagnostic — каждые 4 часа;
- daily admin health summary — 09:30 по timezone приложения.

Проверяются:

- доступность БД;
- production configuration;
- конфигурация четырёх организационных чатов;
- failed task deliveries за 24 часа;
- отрицательные итоговые point balances;
- backup freshness/status/restore verification;
- наличие независимого encrypted S3-compatible backup;
- в full режиме — Telegram Bot API и доступ бота к настроенным чатам.

Health score хранится в БД. Состояния: `healthy`, `degraded`, `critical`.

## 4. Incident engine

- Runtime defect дедуплицируется по стабильному `dedupe_key`.
- Хранятся first/last seen, occurrence count, severity, status, current commit и last healthy commit.
- High/Critical incidents отправляются администраторам в Telegram.
- После восстановления отправляется recovery notification.
- Один дефект не создаёт новый incident каждые 15 минут.
- Fix prompt формируется сервером.
- Перед сохранением diagnostic details/fix prompt проходят sanitizer для token/secret/password/API key/DB URL/URL-shaped данных.
- Telegram initData, cookies, DB credentials и backup bytes в incident payload не сохраняются.

## 5. Admin Mode → Система

Добавлен рабочий System screen:

- health score;
- latest heartbeat/full diagnostic;
- checks;
- incidents и occurrence count;
- commit context;
- «Скопировать промпт для исправления»;
- Backup History;
- ручной full diagnostic;
- loading/error/empty states.

System API защищён backend full-admin authorization. Frontend role не является источником прав. Manual diagnostic rate-limited.

## 6. Backup hardening

Pipeline:

`pg_dump → SHA-256 → isolated restore verification → encryption → persistence`.

Сырой production dump не сохраняется как persistent artifact.

Перед persistence пакет шифруется AES-256-CBC + PBKDF2 (200000 iterations), после чего raw dump и manifest удаляются.

Storage layers:

1. encrypted GitHub Actions artifact — fallback;
2. encrypted S3-compatible external storage — целевой независимый слой.

Для external storage реализован exact-count retention:

- 7 daily;
- 4 weekly;
- 6 monthly;
- 3 manual.

Successful backup callback ERA API принимается только при наличии checksum, storage reference и `restore_verified_at`.

Callback защищён отдельным `BACKUP_REPORT_SECRET` через constant-time comparison. Failure создаёт/обновляет System Incident; следующий successful verified backup закрывает его и создаёт recovery notification.

## 7. Backup readiness semantics

System не приравнивает GitHub fallback к полноценному independent backup:

- нет Backup History → warning;
- failed/unverified backup → High;
- verified backup старше 36h → High;
- verified backup старше 72h → Critical;
- свежий verified GitHub-only backup → warning;
- свежий verified `s3-compatible-encrypted` backup → PASS.

Это исключает ложный `100/100`, когда код backup существует, а независимое хранилище фактически не подключено.

## 8. Production integration

- Docker production entrypoint выполняет `alembic upgrade heads` до запуска `uvicorn app.webapp:app`.
- System scheduler подключён именно к `app.webapp` lifespan, а не только polling process.
- Существующие `/health`, `/ready`, `/diag`, webhook и security middleware сохранены.
- Изменение `webapp.py` для System scheduler точечное: import + registration jobs.

## 9. Regression/security coverage

Добавлены проверки для:

- sanitization secret-shaped diagnostic content;
- critical health scoring;
- регистрации heartbeat/full/daily jobs;
- запрета participant access к System API;
- invalid backup-report secret;
- Community deep links;
- browser history navigation.

Release запрещён при красных mandatory checks.

## 10. Новые production secrets

### Render

- `BACKUP_REPORT_SECRET` — `sync: false`, значение не хранится в репозитории.

### GitHub Actions

Минимум для database backup:

- `BACKUP_DATABASE_URL`.

Рекомендуемый отдельный encryption secret:

- `BACKUP_ENCRYPTION_KEY`.

Для Backup History/Telegram notifications:

- `BACKUP_REPORT_URL`;
- `BACKUP_REPORT_SECRET` — то же значение, что в Render.

Для полного independent backup:

- `BACKUP_S3_BUCKET`;
- `BACKUP_S3_ACCESS_KEY_ID`;
- `BACKUP_S3_SECRET_ACCESS_KEY`;
- `BACKUP_S3_REGION` — optional;
- `BACKUP_S3_ENDPOINT_URL` — optional для S3-compatible provider;
- `BACKUP_S3_PREFIX` — optional.

Подробный restore/runbook: `docs/BACKUP_AND_RECOVERY.md`.

## 11. OWNER ACTION REQUIRED

Следующее нельзя честно отметить PASS одним изменением Git-репозитория:

1. проверить/задать реальный `BACKUP_DATABASE_URL` в GitHub Actions;
2. задать одинаковый `BACKUP_REPORT_SECRET` в Render и GitHub и `BACKUP_REPORT_URL` в GitHub;
3. создать и настроить реальный S3-compatible bucket/credentials;
4. получить первый successful production backup после изменений;
5. выполнить реальный restore из внешней encrypted copy;
6. включить/проверить GitHub branch protection для `main` — API текущей интеграции возвращает `403 Resource not accessible by integration`;
7. завершить legal review privacy/consent/minors policy;
8. выполнить финальный click-through на реальном Telegram client/device.

Это внешняя конфигурация/юридическая/операционная приёмка, а не скрытые недоделанные функции.

## 12. Release gate

PR/release можно merge-ить только если зелёные:

- Python compile;
- correctness lint;
- Python dependency audit;
- pytest;
- frontend typecheck/build;
- npm audit;
- E2E;
- gitleaks full-history;
- Alembic single head.

После merge production acceptance подтверждается только если одновременно:

- `/health` показывает release commit;
- `/ready` = ready;
- Admin Mode → Система выполняет full diagnostic;
- нет unresolved Critical/High runtime incidents;
- backup callback получил successful verified backup;
- external storage provider = `s3-compatible-encrypted`;
- выполнен restore drill;
- owner actions выше закрыты либо риск явно принят владельцем.

## Итог

Финальный кодовый блок master-spec реализован: health, incidents, backup metadata и recovery стали частью самой ERA Platform, а ключевая навигация получила route/history semantics.

**Текущий честный статус до внешней настройки: `CODE COMPLETE — NOT YET FULLY PRODUCTION-ACCEPTED`.**
