# ERA Platform — Deployment Runbook

Цель: новый разработчик или дежурный админ может развернуть/обновить/
откатить сервис, не читая историю всех PR. Всё ниже соответствует
реальным файлам репозитория (`render.yaml`, `Dockerfile`,
`.github/workflows/`), а не гипотетической инфраструктуре.

## Топология

Один процесс (`app/webapp.py`), один Postgres, один Redis:

- Бот (aiogram, long-polling заменён на webhook) и Mini App API
  (`/api/v1/*`) — один и тот же FastAPI-процесс, один и тот же `Bot`.
- Mini App фронтенд собирается на этапе Docker-сборки (`Dockerfile`,
  Node-стадия) и раздаётся тем же процессом как статика на `/app`.
- Postgres — единственное хранилище пользовательских данных.
- Redis — только для aiogram FSM storage (состояния диалогов бота), не
  для бизнес-данных.

## Требования к серверу

- Согласно `render.yaml`: Render Web Service, `runtime: docker`, план
  `free` (можно повысить). Регион `frankfurt`.
- Postgres: Render managed database `era-postgres`.
- Redis/Key-Value: Render managed `era-redis`.
- Через Docker-образ подходит и любой другой хост, поддерживающий
  Dockerfile + переменные окружения (сервис не завязан на Render API).

## Переменные окружения

Полный список — `.env.example`. Обязательные для реального запуска:

| Переменная | Обязательна | Комментарий |
|---|---|---|
| `BOT_TOKEN` | да | из @BotFather; ≥10 символов, иначе `Settings` не соберётся |
| `DATABASE_URL` | да | `postgresql+asyncpg://...` (Render даёт `postgresql://`, конвертируется автоматически) |
| `REDIS_URL` | да | FSM storage |
| `PUBLIC_BASE_URL` | да для вебхука/Mini App | если пусто, используется `RENDER_EXTERNAL_HOSTNAME` (Render подставляет сам) |
| `WEBHOOK_SECRET` | рекомендуется | `render.yaml`: `generateValue: true` — Render сам генерирует при Blueprint-синхронизации |
| `MINIAPP_AUTH_SECRET` | **обязательна для Mini App** | без неё кнопка "Открыть ЭРА" скрыта, `/api/v1/miniapp/auth` вернёт 500 |
| `DEV_AUTH_ENABLED` | **должна быть `false`/не задана в проде** | если `true` на Render — приложение теперь **не запустится** (см. `Settings.assert_safe_for_deployment`, этот блок) |
| `ADMIN_IDS` | да | Telegram ID через запятую — основные администраторы |
| `ERA_CHANNEL_ID`, `GENERAL_CHAT_ID`, `INTERNAL_DEPARTMENT_CHAT_ID`, `EXTERNAL_DEPARTMENT_CHAT_ID`, `LEADERS_CHAT_ID` | для чат-модерации | без них `chat_access_service` просто не управляет соответствующим чатом (`chat_key_for_id` вернёт `None`) |
| `OPENAI_API_KEY` | для ИИ-подсказок в боте | без неё — контролируемый fallback (см. `AIUnavailableError`), не падение |

**Важно про `MINIAPP_AUTH_SECRET`**: `render.yaml` объявляет
`generateValue: true`, но это применяется только при **Blueprint sync**,
а не при обычном git-push деплое уже существующего сервиса. Проверить
Render Dashboard → Environment для сервиса — если переменной нет,
синхронизировать blueprint или задать вручную.

**Это не гипотетический риск — подтверждено на реальном проде (PR21/22,
через новый `/diag`-эндпоинт)**: `GET /diag` вернул
`"miniapp_configured": false` на боевом сервисе. Это означает, что
`MINIAPP_AUTH_SECRET` (или `MINIAPP_URL`) сейчас **фактически не задана**
на Render, и поэтому кнопка "Открыть ЭРА" отсутствует **во всех формах**
одновременно (chat menu button, reply-keyboard кнопка в `main_menu()`,
inline-кнопка в `main_inline_keyboard()`) — не из-за бага в коде, а
потому что `Settings.effective_miniapp_url` по дизайну возвращает пустую
строку, пока эта переменная не задана (см. её docstring в
`app/config.py`). Это ровно та причина, из-за которой Mini App-кнопка
не появлялась ни до, ни после всех фиксов маршрутизации в PR21 —
единственное, что нужно сделать: **зайти в Render Dashboard →
`era-telegram-bot` → Environment и убедиться, что `MINIAPP_AUTH_SECRET`
(или явный `MINIAPP_URL`) реально присутствует и не пуста** — если её
нет, синхронизировать blueprint (тогда Render сгенерирует значение
автоматически) либо задать вручную. После сохранения переменной Render
сам перезапустит сервис — новый запуск подхватит её без дополнительных
действий с моей стороны. Проверить результат: `curl
https://<host>/diag` должен показать `"miniapp_configured": true`.

## Создание базы

Управляется Render (`databases:` в `render.yaml`) либо любым Postgres 14+.
Приложение само накатывает миграции при старте контейнера — отдельный шаг
"создать таблицы" не нужен и не должен выполняться вручную.

## Запуск миграций

Встроено в `CMD` контейнера (`Dockerfile`):

```
alembic upgrade heads && uvicorn app.webapp:app --host 0.0.0.0 --port ${PORT:-8000}
```

Если после деплоя сервис не поднимается — первым делом смотреть логи
именно на `alembic upgrade heads` (несовместимая миграция остановит запуск
до старта uvicorn, что безопаснее, чем частично мигрированная база под
нагрузкой).

Перед мёржем любого PR с миграцией обязательно (см. `docs/ERA_PLATFORM_PROGRESS.md`):

- один Alembic head (`python -m alembic heads`);
- upgrade/downgrade smoke-тест на временной SQLite/Postgres.

## Сборка frontend

Автоматическая, часть `docker build` (Node-стадия в `Dockerfile`). Локально:

```bash
cd frontend
npm ci
npm run build   # tsc + vite build → frontend/dist
```

Если `frontend/dist` отсутствует локально — бот и API продолжают
работать, просто `/app` не примонтирован (см. `_mount_frontend` в
`app/webapp.py`, намеренно не бросает исключение).

## Запуск backend локально

```bash
pip install -r requirements.txt
alembic upgrade heads
uvicorn app.webapp:app --reload
```

Требуется работающий Postgres и Redis (см. `docker-compose.yml`, если
есть, либо локальные инстансы по `DATABASE_URL`/`REDIS_URL`).

## Настройка Telegram

1. Токен от @BotFather → `BOT_TOKEN`.
2. Домен/URL Mini App регистрируется в @BotFather (`/newapp` или
   `/setmenubutton`) — приложение **не может сделать это само**, только
   владелец бота через BotFather.
3. Вебхук выставляется приложением автоматически при старте
   (`app/webapp.py::lifespan`), используя `PUBLIC_BASE_URL`/
   `RENDER_EXTERNAL_HOSTNAME` — вручную дёргать Telegram Bot API не нужно.

## Настройка домена и HTTPS

- На Render: HTTPS уже терминируется платформой на
  `*.onrender.com`-домене или подключённом кастомном домене — отдельная
  настройка сертификата не требуется на этом провайдере.
- Если сервис переносится на другой хостинг — обязателен reverse proxy
  (nginx/Caddy/Cloudflare) с TLS до того, как открывать `/telegram/webhook`
  и `/api/v1/*` наружу; Telegram отклоняет вебхуки на голом HTTP.

## Smoke test после деплоя

```bash
curl -s https://<host>/health   # {"status":"ok", "version":..., "commit":...}
curl -s https://<host>/ready    # {"status":"ready"} — требует реального подключения к БД
```

`/health` — чистый liveness (не трогает БД/Redis, отвечает даже при их
деградации — так и задумано). `/ready` (добавлен в этом блоке) —
реальная проверка подключения к БД, не раскрывает конфигурацию в ответе.
Дополнительно проверить в самом Telegram: команда `/start` в личке с
ботом и открытие кнопки "Открыть ЭРА" в Mini App.

## Обновление версии

Стандартный git-flow этого репозитория (см. `docs/ERA_PLATFORM_PROGRESS.md`):
ветка → PR → зелёный CI (оба workflow) → merge в `main` → Render
подхватывает `main` автоматически (`autoDeployTrigger: commit`).

## Rollback

1. В Render Dashboard → Deploys выбрать предыдущий успешный деплой и
   "Rollback" (Render хранит историю образов).
2. Если проблема — в миграции, а не в коде: миграции этого репозитория
   обязаны быть additive/reversible (см. `docs/ERA_PLATFORM_PROGRESS.md`
   правила), т.е. `alembic downgrade -1` безопасен без потери
   пользовательских данных, накопленных **до** проблемной миграции.
   Данные, записанные **после** применения проблемной миграции в новые
   колонки/таблицы, откатом миграции не восстанавливаются — если это
   критично, восстанавливаться из бэкапа (`docs/BACKUP_AND_RECOVERY.md`).
3. Секреты не трогать при обычном rollback — они не версионируются вместе
   с кодом.

## Восстановление

См. `docs/BACKUP_AND_RECOVERY.md` — отдельный документ, там же описан
уже работающий автоматический ежедневный backup + verify-restore.

## Диагностика типовых ошибок

| Симптом | Вероятная причина | Что проверить |
|---|---|---|
| Кнопка "Открыть ЭРА" не появляется в боте | `MINIAPP_AUTH_SECRET` не задана | Render → Environment; см. раздел выше |
| `/api/v1/miniapp/auth` → 500 `miniapp_auth_not_configured` | то же самое | то же самое |
| `/api/v1/miniapp/auth` → 401 `invalid_signature` | `initData` подписан не тем `BOT_TOKEN`, или Mini App открыт не через настоящий Telegram-клиент | Сверить `BOT_TOKEN` на сервере с тем, что в @BotFather |
| Приложение не стартует, лог: `DEV_AUTH_ENABLED=true ... Refusing to start` | Переменная `DEV_AUTH_ENABLED` случайно включена на Render | Убрать/установить `false` в Render Environment (это защита, добавленная в этом блоке — см. `docs/PRODUCTION_READINESS_AUDIT.md`, находка №2) |
| `/ready` возвращает 503 | БД недоступна или ещё не готова | Проверить статус Render Postgres, `alembic upgrade heads` в логах старта |
| Вебхук не приходит от Telegram | `PUBLIC_BASE_URL` не настроен, либо TLS/домен сломан | Логи старта: `PUBLIC_BASE_URL is not set; Telegram webhook is disabled` |
| Пользователь не может писать в общий чат после одобрения | Временная недоступность Telegram API во время `sync_user_chat_access` | Проверить `audit_logs` на `chat_access.synced` с `failed > 0` для этого пользователя (добавлено в этом блоке) — при `failed > 0` синхронизация не удалась, нужен повторный вызов (переодобрить/перезаблокировать пользователя, чтобы триггернуть повторный sync) |
