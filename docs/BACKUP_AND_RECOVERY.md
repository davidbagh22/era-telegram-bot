# Резервное копирование и восстановление PostgreSQL

## Цель

Защитить рабочие данные Telegram-бота и Mini App «ЭРА» от удаления, повреждения базы, ошибочной миграции и сбоя инфраструктуры без хранения открытого dump в Git и без передачи production DB credentials в GitHub Actions.

## Политика

| Параметр | Значение |
|---|---|
| Частота | ежедневно в 01:17 UTC |
| Формат исходной копии | PostgreSQL custom dump |
| Production snapshot | создаётся внутри Render-сервиса по внутреннему `DATABASE_URL` |
| Авторизация GitHub → ERA | GitHub OIDC, short-lived token, exact repo/main/workflow claims |
| Проверка | автоматическое восстановление в изолированную PostgreSQL на GitHub runner |
| Контроль целостности | SHA-256 до restore и для зашифрованного архива |
| Шифрование перед persistence | AES-256-CBC + PBKDF2, 200000 итераций |
| Основной off-Render fallback | только зашифрованный GitHub Actions artifact |
| Дополнительное внешнее хранилище | S3-совместимое, только зашифрованный архив |
| Retention S3 | 7 daily / 4 weekly / 6 monthly |
| RPO | не более 24 часов |
| Целевой RTO | до 2 часов |

## Почему GitHub OIDC

Статические `BACKUP_DATABASE_URL` и `BACKUP_REPORT_SECRET` удалены из production-контракта.

Workflow получает краткоживущий GitHub OIDC token и production принимает его только если одновременно совпадают:

- repository `davidbagh22/era-telegram-bot`;
- repository ID;
- ref `refs/heads/main`;
- конкретный `.github/workflows/database-backup.yml`;
- event `schedule` или `workflow_dispatch`;
- `github-hosted` runner;
- audience `era-platform-backup`;
- подпись GitHub, issuer и срок действия JWT.

Неверный repo, fork, feature branch, другой workflow или self-hosted runner не получает snapshot/material/report доступ.

## Что считается успешным backup

Backup считается успешным только после всех шагов:

1. GitHub workflow получает корректную OIDC identity;
2. production создаёт transient `pg_dump` через внутреннее подключение к Render Postgres;
3. snapshot передаётся только по HTTPS авторизованному workflow;
4. локальный SHA-256 совпадает с checksum production snapshot;
5. dump восстановлен в отдельную PostgreSQL на GitHub runner;
6. обязательная таблица `users` присутствует после restore;
7. только после успешного restore transient dump шифруется;
8. raw dump удаляется;
9. зашифрованная копия сохраняется вне Render;
10. ERA Backup History получает checksum, storage reference и `restore_verified_at` через OIDC-authenticated callback.

Endpoint не принимает success-отчёт без checksum, storage reference и факта restore verification.

## Ключ шифрования

`MINIAPP_AUTH_SECRET` не передаётся в GitHub.

Production выводит из него отдельный one-purpose backup key через HMAC-SHA256 с domain separation `era-platform-backup-encryption-v1`. Только этот производный ключ отдаётся уже проверенному exact GitHub OIDC workflow через `Cache-Control: no-store` endpoint.

При плановой ротации `MINIAPP_AUTH_SECRET` перед ротацией необходимо сохранить возможность расшифровки старых backup или выполнить новый полный verified backup и обновить recovery material. Сам root secret в backup metadata/logs не записывается.

## GitHub Actions secrets

Для базового ежедневного verified backup **не нужны**:

- `BACKUP_DATABASE_URL`;
- `BACKUP_REPORT_SECRET`;
- `BACKUP_REPORT_URL`;
- `BACKUP_ENCRYPTION_KEY`.

GitHub получает только short-lived OIDC token для текущего job. Production DB credentials никогда не покидают Render.

## Внешнее S3-совместимое хранилище

Опционально для дополнительной второй off-Render копии и exact-count retention:

- `BACKUP_S3_BUCKET`;
- `BACKUP_S3_ACCESS_KEY_ID`;
- `BACKUP_S3_SECRET_ACCESS_KEY`;
- `BACKUP_S3_REGION` — при необходимости;
- `BACKUP_S3_ENDPOINT_URL` — для Cloudflare R2 / MinIO / другого S3-compatible provider;
- `BACKUP_S3_PREFIX` — опционально.

Без S3 ежедневный backup всё равно считается рабочим, если restore verification успешно завершён и зашифрованный GitHub Actions artifact создан. S3 — дополнительный независимый слой, а не причина останавливать основной backup.

## Admin Mode → Система

Система показывает:

- последний backup;
- тип daily / weekly / monthly / manual;
- status;
- restore verification;
- storage provider;
- Backup History;
- stale backup как incident;
- workflow failure как incident;
- recovery после следующего successful verified backup.

High/critical backup incident отправляется администраторам через Telegram и дедуплицируется.

## Восстановление

Восстановление сначала проводится только в новой тестовой базе.

Для зашифрованной GitHub/S3 копии получить текущий recovery key контролируемым администраторским процессом; не передавать его в issue, PR, Telegram, аргументы командной строки или shell history. После расшифровки:

```bash
export RESTORE_DATABASE_URL='postgresql://.../era_restore_test'
export BACKUP_FILE='backups/era-YYYYMMDDTHHMMSSZ.dump'
export BACKUP_SHA256='sha256 исходного dump'
./scripts/verify_database_restore.sh
```

Проверить пользователей, транзакции баллов, мероприятия, регистрации, связи, Alembic revision, `/health`, `/ready` и ключевые Mini App flows.

## Откат

1. Остановить новые записи в повреждённую базу.
2. Создать аварийный snapshot текущего состояния, если база читается.
3. Развернуть последнюю verified копию в новой БД.
4. Сверить Alembic revision и выполнить только необходимые миграции.
5. Проверить ключевые таблицы и балансы.
6. Обновить `DATABASE_URL` в Render.
7. Перезапустить сервис и проверить `/health`, `/ready`, System diagnostics.
8. Зафиксировать incident и фактический RPO/RTO.

## Квартальная restore drill

Раз в три месяца выполнить полное восстановление из зашифрованной off-Render копии и зафиксировать дату, provider, checksum, время восстановления, найденные отклонения и фактические RPO/RTO.
