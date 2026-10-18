# ЭРА: точный остаток после релизов #342–#350

Реализованный код и протокол выпуска: [PR #344](https://github.com/davidbagh22/era-telegram-bot/pull/344); доказательства — FUNCTIONAL_MATRIX.md, NATIVE_ADMIN_GUIDE.md и RELEASE.md. Повторно не делать кнопки, native заявки, базовые сводки, автокоманды, composer, QR v2, редакционную очередь, campaign controls и SLA.

## Обязательная реальная приёмка

Вход исполнителя в Telegram владельца не разрешён. Нельзя создавать фиктивных production-игроков, события или посещения. Блокер снимается действиями реальных людей:

- /start администратора: постоянные «📊 Статистика», «Заявки», «Открыть ЭРА»; новая сводка не перезаписывает главное меню. Литература и игры доступны внутри «Досуг».
- Настоящая заявка: полная карточка, одобрение/отказ/уточнение; ожидающий chat join принимается при одобрении; старые кнопки не меняют решение.
- Два одобренных участника: автокоманды А/Б, Telegram-имена и ID, готовность, один public message_id, личная карточка состава, персональный результат. Одиночные ответы — только в личном боте.
- Реальное событие: текст с фото/фото отдельно, изменение даты/лимита, preview, /cancel → resume, одна публикация в прежнюю тему. После события QR/код/manual и повтор — одно посещение и одна награда.
- Плановая сводка в 09:00 МСК: один delivery receipt на адресата/период; native кнопки и Excel. До фактической отправки не отмечать её принятой.
- Canary кампании на согласованных получателях: pause → resume без дублей, отмена оставшихся адресатов; массовую рассылку как тест не запускать.

Пути: app/handlers/registration.py, app/handlers/admin/application_review_bot.py, app/services/application_review_service.py, app/handlers/era_game_room.py, app/handlers/leader/events_block6.py, app/services/event_attendance_service.py, app/services/admin_analytics_service.py.

## Категории, ответственный и переписка обращений

После #344 подготовлена совместимая миграция 0062_support_threads и полный текстовый диалог: личная история, категории, взятие в работу, закрытие/открытие, версия карточки, идемпотентные реплики и SLA по текущему ожиданию. Протокол, ограничения и canary — SUPPORT_THREADS_RELEASE.md. Не повторять эту реализацию; готовность выпуска определяется CI и Render окончательного коммита.

Пути: app/database/models.py::UserQuestion, app/handlers/admin/support_bot.py::{show_inbox,support_item,support_answer}, app/services/scheduler_service.py::{deliver_support_answers,send_review_sla_reminders}, app/handlers/participant/questions.py::{question_start,_save_question}, app/services/support_service.py::{create_support_question,deliver_support_intake_notices}, app/services/admin_dashboard_service.py.

В дополнении 18.10 реализованы файлы в ответах/дополнениях, последняя страница истории и выбор другого действующего администратора с durable уведомлением; см. SUPPORT_THREADS_RELEASE.md. Осталось: canary реального участника и администратора перед ALL и scoped модераторы вместе с permission matrix. Не обещать анонимность — текущая карточка прямо сообщает, кто видит переписку. При неясной доставке требуется сверка, а не повторная отправка.

Приёмка: два администратора не перезаписывают ответ; два одинаковых webhook не создают две реплики; одинаковый текст в разных раундах переписки доставляется отдельно; чужой участник не читает ticket; повтор после рестарта не дублируется. Любая схема — additive migration, isolated upgrade/restore и безопасный rollback без удаления новых сообщений.

## Reviewer проектов и полный маршрут задач

Пути: app/database/models.py::Project, app/services/project_service.py, project_* services, app/handlers/admin/projects_block5_list.py, projects_block5_decision.py, app/services/task_service.py, app/services/scheduler_service.py.

Установить фактического назначенного согласующего через действующие roles/grants; проверить quick и 17-step forms, черновик, доработку, history, reminders и escalations. Существующие initial-review 72/144ч и venue reminder не дублировать. Для задач пройти assign/open-response/deadline/comments/complete/review и параллельное подтверждение с одним award через points_service. Внешний AI при ошибке оставляет ручной путь и сохранённые данные.

Приёмка: автор/исполнитель/проверяющий проходят полный цикл, scoped права проверены сервером, stale decision отклоняется, restart не повторяет reminder/reward. Новые поля reviewer — только совместимой миграцией.

## Полная delegated access matrix

Пути: app/services/authorization_service.py, leadership_permission_service.py, app/middlewares/admin_bot_access.py, app/handlers/admin/__init__.py, docs/ROLE_PERMISSION_MATRIX.md.

Сопоставить суперадминистратора/админа/руководителя/редакторов/модераторов существующим permission grants и scope. Не расширять корневой admin router одним общим «любой grant»: это откроет legacy handlers. Для каждого делегированного действия нужны owner handler, private-chat filter, серверный permission/scope check и отрицательные тесты. Не снимать чужие ограничения. Старые #250/#253/#282 с permission writes не объединять.

## Редакционная программа и дополнительные рубрики

Пути: app/services/book_club_service.py::{save_editorial_item,approve_editorial_item,publish_editorial_item,run_editorial_queue}, app/handlers/admin/literature_editor.py, app/services/daily_public_content_service.py.

Инфраструктура готова; очередь выключена. Требуются утверждённые человеком материалы русских/современных/армянских авторов и календарь. Сначала 2–3 дополнительные рубрики по существующей инфраструктуре, с возможностью выключения/подписки и контролем шумности. Проверенные тексты утверждать через native editor. Не подменять утверждение автоматически сгенерированным контентом и не включать все рубрики.

Приёмка: реальный editor-approved выпуск в прежнюю тему, restart без дубля, opt-in DM, pause/resume, отсутствие автоматики для drafts. При uncertain — сверка существующего сообщения, без слепой повторной отправки.

## Политика данных, independent backup и Phase 8

- app/services/consent_service.py, docs/DATA_INVENTORY.md: владелец утверждает применимый текст, version и процедуру для несовершеннолетних. Техническое согласие не является юридической экспертизой. Проверить выгрузку/запрос удаления, не удаляя ledger/историю без установленного основания.
- .github/workflows/database-backup.yml, scripts/verify_database_restore.sh, backup service: encrypted GitHub fallback и isolated restore работают. Подключить независимое S3-совместимое хранилище через штатные secrets и проверить restore именно оттуда. Секреты в чат не передавать.
- Сертификаты/portfolio PDF, Calendar, сезоны, армянская/английская локализация: сначала принять базовые процессы, затем проверить реальные существующие реализации. Наличие кода не считать готовностью.
- Persistent menu: после bounded verification контролировать диагностический reason в Render. Не игнорировать origin/type mismatch и не ослаблять Telegram initData. Ни новый бот, ни новая Mini App не создавались.

## Рабочая копия и автоматическая проверка

17 октября локальный исполнитель восстановлен. Создана отдельная чистая рабочая копия актуального PR #346; 50 целевых тестов и 12 subtests прошли локально. Старые незавершённые рабочие копии не перезаписывались. Доказательство выпуска — успешный CI окончательного head и подтверждённый Render, а не прежние прерванные прогоны. Недоступность локального исполнителя больше не является блокером остатка ТЗ.
