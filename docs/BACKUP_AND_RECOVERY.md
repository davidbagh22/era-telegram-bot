# Резервное копирование и восстановление PostgreSQL

## Цель

Защитить рабочие данные Telegram-бота и Mini App «ЭРА» от удаления, повреждения базы, ошибочной миграции и сбоя инфраструктуры без хранения открытого dump в Git или публичном artifact.

## Политика

| Параметр | Значение |
|---|---|
| Частота | ежедневно в 01:17 UTC |
| Формат исходной копии | PostgreSQL custom dump |
| Проверка | автоматическое восстановление в изолированную PostgreSQL |
| Контроль целостности | SHA-256 до restore и для зашифрованного архива |
| Шифрование перед persistence | AES-256-CBC + PBKDF2, 200000 итераций |
| GitHub fallback | только зашифрованный artifact |
| Внешнее хранилище | S3-совместимое, только зашифрованный архив |
| Retention во внешнем хранилище | 7 daily / 4 weekly / 6 monthly |
| RPO | не более 24 часов |
| Целевой RTO | до 2 часов |

## Что считается успешным backup

Backup считается успешным только после всех шагов:

1. `pg_dump` завершён без ошибки;
2. создан непустой custom dump;
3. SHA-256 исходного dump совпал;
4. dump восстановлен в отдельную временную PostgreSQL;
5. обязательная таблица `users` присутствует после restore;
6. dump + manifest зашифрованы до отправки в persistent storage;
7. создана зашифрованная persistent copy;
8. в ERA Backup History при настроенном callback записаны checksum, storage reference и `restore_verified_at`.

Endpoint не принимает success-отчёт без checksum, storage reference и факта restore verification.

## GitHub Actions secrets

Минимально необходим:

- `BACKUP_DATABASE_URL` — внешняя строка подключения PostgreSQL для backup.

Рекомендуемый отдельный ключ шифрования:

- `BACKUP_ENCRYPTION_KEY`.

Если он ещё не настроен, workflow не сохраняет сырой dump: временно используется детерминированный ключ, производный от `BACKUP_DATABASE_URL`. Это режим совместимости, а не целевая конфигурация. Для нормальной ротации и восстановления должен использоваться отдельный `BACKUP_ENCRYPTION_KEY`.

Для Backup History и Telegram-уведомлений:

- `BACKUP_REPORT_URL` — полный URL `/api/v1/internal/backup/report` production-сервиса;
- `BACKUP_REPORT_SECRET` — тот же секрет, что `BACKUP_REPORT_SECRET` в Render.

Эти два параметра задаются вместе. Callback передаёт только metadata; `DATABASE_URL`, ключ шифрования и backup bytes через API не отправляются.

## Внешнее S3-совместимое хранилище

Для независимой копии и точного retention настроить:

- `BACKUP_S3_BUCKET`;
- `BACKUP_S3_ACCESS_KEY_ID`;
- `BACKUP_S3_SECRET_ACCESS_KEY`;
- `BACKUP_S3_REGION` — при необходимости;
- `BACKUP_S3_ENDPOINT_URL` — для Cloudflare R2 / MinIO / другого S3-compatible provider;
- `BACKUP_S3_PREFIX` — опционально, по умолчанию `era-backups`.

Bucket, access key и secret key задаются все вместе. Если они отсутствуют, ежедневная копия всё равно проходит restore verification и сохраняется только как зашифрованный GitHub artifact, но это **не считается полным независимым backup-контуром**.

`scripts/store_encrypted_backup_s3.sh` после каждой успешной загрузки удаляет только старые объекты соответствующего tier:

- `daily` — хранить последние 7;
- `weekly` — последние 4;
- `monthly` — последние 6;
- `manual` — последние 3.

Provider lifecycle policy можно сделать строже, но она не должна удалять объекты раньше этих сроков.

## Render

В production service должны быть:

- `DATABASE_URL`;
- `BACKUP_REPORT_SECRET` — если включён callback;
- стандартные секреты приложения.

`BACKUP_REPORT_SECRET` нельзя писать в issue, PR, README со значением, логи или Telegram.

## Admin Mode → Система

При настроенном callback система показывает:

- последний backup;
- тип daily / weekly / monthly / manual;
- status;
- restore verification;
- storage provider;
- Backup History;
- stale backup как incident;
- failure как отдельный incident;
- recovery после следующего успешного verified backup.

High/critical backup incident отправляется администраторам через Telegram. Повторяющаяся одна и та же проблема дедуплицируется, а не создаёт новый incident каждые 15 минут.

## Восстановление

Восстановление сначала проводится только в новой тестовой базе.

Для зашифрованного архива сначала расшифровать его локально в защищённой среде с тем ключом, которым он был создан. Ключ не должен передаваться в командной строке или сохраняться в shell history; использовать переменную окружения или secret manager.

После извлечения dump:

```bash
export RESTORE_DATABASE_URL='postgresql://.../era_restore_test'
export BACKUP_FILE='backups/era-postgres-YYYYMMDDTHHMMSSZ.dump'
export BACKUP_SHA256='значение исходного dump из manifest'
./scripts/verify_database_restore.sh
```

После восстановления проверить:

- количество пользователей;
- количество транзакций баллов;
- количество мероприятий и регистраций;
- связи пользователей, департаментов и направлений;
- отсутствие необъяснимых отрицательных балансов;
- текущую версию Alembic;
- запуск API/бота на тестовой строке подключения;
- `/health`, `/ready` и ключевые Mini App flows.

Переключать production на восстановленную базу можно только после фиксации причины инцидента, сохранения аварийной копии повреждённой базы и подтверждения владельца проекта.

## Откат

1. Остановить новые записи в повреждённую базу.
2. Создать аварийный dump текущего состояния, если база ещё читается.
3. Развернуть последнюю проверенную копию в новой базе.
4. Выполнить миграции только после сверки версии схемы.
5. Проверить ключевые таблицы и балансы.
6. Обновить `DATABASE_URL` в Render.
7. Перезапустить сервис и проверить `/health`, `/ready`, System diagnostics.
8. Сохранить incident и фактический RPO/RTO.

## Квартальная restore drill

Раз в три месяца выполнить полное учебное восстановление из **внешней** зашифрованной копии и зафиксировать:

- дату копии;
- storage provider;
- время восстановления;
- результат checksum/restore проверки;
- найденные отклонения;
- фактический RPO и RTO.

## Ограничения инфраструктуры

Код не может сам создать S3 bucket или установить GitHub/Render secret. До настройки внешнего storage и общего `BACKUP_REPORT_SECRET` система продолжает делать безопасный зашифрованный GitHub backup, но Admin System обязан считать внешний backup-контур незавершённым, а не маркировать его как полный production-ready backup.
