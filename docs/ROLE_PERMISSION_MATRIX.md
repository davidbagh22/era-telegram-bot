# ROLE PERMISSION MATRIX

Матрица фиксирует фактическое поведение кода после этапа "Роли и права".

## Источники прав

- `users.role` — широкая роль пользователя: participant, activist, leader, head, council, admin.
- `settings.admin_ids` — основные администраторы из конфигурации. Они имеют полный административный доступ независимо от `users.role`.
- `permission_grants` — точечные глобальные права, которые дают доступ к отдельным административным действиям.
- `is_blocked` и `is_archived` отключают доступ для ролей и delegated permissions. Основные администраторы из `settings.admin_ids` защищены от блокировки и архивации через бота.
- `application_status == approved` нужен для пользовательских сценариев участника: проекты, задачи, награды, опросы, обращения.

## Широкая матрица

| Действие | Участник | Активный | Лидер | Руководитель | Администратор | Основной администратор |
|---|---:|---:|---:|---:|---:|---:|
| Пользовательское меню | да | да | да | да | да | да |
| Личный кабинет, проекты, задачи участника | после одобрения заявки | после одобрения заявки | после одобрения заявки | после одобрения заявки | после одобрения заявки | после одобрения заявки |
| Меню лидера | нет | нет | да | да | да | да |
| Чат лидеров в `/links` | нет | нет | да | да | да | да |
| Панель администратора | только с `panel.view` или другим delegated permission | только с delegated permission | только с delegated permission | только с delegated permission | да | да |
| Просмотр участников | `people.view` или `people.manage` | `people.view` или `people.manage` | `people.view` или `people.manage` | `people.view` или `people.manage` | да | да |
| Управление участниками | `people.manage` | `people.manage` | `people.manage` | `people.manage` | да | да |
| Смена ролей | `people.manage`, кроме назначения admin | `people.manage`, кроме назначения admin | `people.manage`, кроме назначения admin | `people.manage`, кроме назначения admin | да | да |
| Назначение администратора | нет | нет | нет | нет | да | да |
| Изменение technical permissions | нет | нет | нет | нет | да | да |
| Управление мероприятиями | `events.manage` | `events.manage` | `events.manage` | `events.manage` | да | да |
| Управление задачами | `tasks.manage` | `tasks.manage` | `tasks.manage` | `tasks.manage` | да | да |
| Управление проектами | `projects.review` | `projects.review` | `projects.review` | `projects.review` | да | да |
| Партнёры и партнёрские предложения | `partners.manage` | `partners.manage` | `partners.manage` | `partners.manage` | да | да |
| Аналитика | `analytics.view` | `analytics.view` | `analytics.view` | `analytics.view` | да | да |
| Начисление баллов и знаков | `points.award` или `people.manage` в активных user-card потоках | `points.award` или `people.manage` | `points.award` или `people.manage` | `points.award` или `people.manage` | да | да |
| Блокировка/архивация пользователя | `people.manage`, кроме защищённых случаев | `people.manage`, кроме защищённых случаев | `people.manage`, кроме защищённых случаев | `people.manage`, кроме защищённых случаев | да, кроме защищённых случаев | да, кроме защищённых случаев |
| `/bind` и настройки чатов | нет | нет | нет | нет | да | да |

## Серверные запреты

- Нельзя менять собственную роль прямым callback.
- Нельзя менять собственные technical permissions.
- Нельзя заблокировать или архивировать собственный доступ.
- Нельзя понизить, заблокировать или архивировать последнего активного администратора.
- Нельзя понизить, заблокировать или архивировать основного администратора из `settings.admin_ids` через бота.
- Блокировка или архив сразу отключает delegated permissions, потому что проверка перечитывает актуального пользователя на каждом update.

## Термины

- "Активный" в матрице соответствует статусу роста участника, а не отдельной роли `Role`: в коде это `ParticipationStatus.ACTIVE_MEMBER`.
- "Руководитель" соответствует `Role.HEAD`.
- "Основной администратор" — Telegram ID из `settings.admin_ids`.
