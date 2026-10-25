# ERA Platform — Authorization Matrix

См. также `docs/ROLE_PERMISSION_MATRIX.md` — более ранний документ,
описывающий ту же ролевую/permission-grant модель для **бота** (меню,
делегированные права, panel.view и т.д.). Этот документ его не заменяет,
а дополняет: фокус здесь — на API/Mini App слое и object-level
authorization для конкретных эндпоинтов, добавленных в PR1–PR12.

Единый источник правды по backend-проверкам доступа. Frontend не является
границей безопасности — каждая строка ниже соответствует реальной проверке
в `app/services/authorization_service.py` (или соседних `can_*`
функциях), которая выполняется на backend независимо от того, что
показывает Mini App.

Принцип по умолчанию — **deny by default**: если ни одно условие не
выполнено, доступ запрещён.

## Роли

| Роль | `User.role` | Где используется |
|---|---|---|
| Участник | `participant` | базовый доступ ко всем "своим" данным |
| Активист | `activist` | как участник; не даёт админ/лидерских прав |
| Лидер | `leader` | входит в `PRIVILEGED_ROLES` |
| Руководитель направления | `head` | входит в `PRIVILEGED_ROLES` |
| Совет | `council` | входит в `PRIVILEGED_ROLES` |
| Администратор | `admin` | `is_full_admin()` — полный доступ везде |

`PRIVILEGED_ROLES = {leader, head, council, admin}` (`app/utils/constants.py`).
`is_leader` в Mini App = `role in PRIVILEGED_ROLES` (см.
`app/api/v1/schemas.py`), т.е. лидер/руководитель/совет и админ.

Дополнительно: точечные `PermissionGrant` (например `events.manage`,
`tasks.manage`, `partners.manage`, `projects.review`, `people.manage`,
`people.view`) можно выдать конкретному пользователю без полной роли
администратора — это отдельный, более узкий канал доступа, не заменяющий
роль.

## Матрица действий

| Действие | Участник | Лидер | Администратор | Ограничение по объекту | Backend-проверка |
|---|---:|---:|---:|---|---|
| Просмотр своего профиля/портфолио | Да | Да | Да | Только собственный (`get_current_user` → `user.id`) | `app/api/v1/profile.py` |
| Просмотр Home/Активности/Возможностей | Да | Да | Да | Только свои заявки/регистрации | `app/api/v1/home.py`, `events.py`, `tasks.py`, `opportunities.py` |
| Создание/редактирование своего проекта | Да (автор) | Да (автор) | Да (автор) | Только автор проекта, пока не отправлен на модерацию | `app/services/project_workflow_service.py` |
| Управление Workspace проекта (роли, задачи, участники) | Нет | Да, только назначенный проект | Да, любой проект | `can_manage_project()` — проверяет, что пользователь — куратор/участник с правом на именно этот `project_id` | `app/services/project_workspace_service.py::can_manage_project` |
| Просмотр Workspace проекта | Только если участник команды | Да, если куратор/участник | Да | `can_view_workspace()` | `project_workspace_service.py::can_view_workspace` |
| Обзор контура лидера (участники/мероприятия/проекты своего департамента) | Нет | Да, только свой департамент/направление (админ — все) | Да | Скоуп строится по `UserDepartment`/`UserDirection` вызывающего | `app/services/leader_service.py::scope_ids` |
| Создание открытой задачи, решение по отклику | Нет | Да, только для задач, которые сам создал | Да | `decide_task_application` проверяет `task.creator_id == actor.id`, иначе `PermissionError` | `app/services/leader_service.py::decide_task_application` |
| Admin Dashboard | Нет | Нет | Да, либо `admin_ids`/роль `admin`, либо ЛЮБОЙ активный `PermissionGrant` | — | `admin_dashboard_service.py::has_dashboard_access` |
| Обработка заявок на регистрацию | Нет | Нет | Да (та же проверка, что Dashboard) | — | `app/api/v1/admin.py::require_dashboard_access` |
| Модерация проектов | Нет | Нет | Да, либо `is_full_admin`, либо грант `projects.review` | — | `project_workspace_service.py::can_review_projects` |
| Модерация мероприятий | Нет | Нет | Да, либо `is_full_admin`, либо грант `events.manage` | — | `authorization_service.py::can_manage_events` |
| Проверка результатов заданий | Нет | Нет | Да, либо `is_full_admin`, либо грант `tasks.manage` | — | `authorization_service.py::can_manage_tasks` |
| Проверка заявок на партнёрские возможности | Нет | Нет | Да, либо `is_full_admin`, либо грант `partners.manage` | — | `authorization_service.py::can_manage_partners` |
| Просмотр списка участников (не своих) | Нет | Да, в рамках своего скоупа | Да, все | `can_view_people()` | `authorization_service.py::can_view_people` |
| Изменение роли/блокировка/архивация участника | Нет | Нет | Да, только `is_full_admin` (не через частичный грант) | Нельзя менять собственную роль/доступ; нельзя понизить/заблокировать последнего или основного (`admin_ids`) администратора | `authorization_service.py::can_change_role`, `can_change_access_status` |
| Выдача/отзыв точечных прав (`PermissionGrant`) | Нет | Нет | Да, только `is_full_admin` | Нельзя менять собственные права | `authorization_service.py::can_manage_permissions`, `can_change_permission` |

## Object-level authorization (защита от IDOR)

Каждый moderation/review endpoint грузит объект по ID из URL и **только
после этого** проверяет права и состояние — ID из фронтенда никогда не
считается достаточным основанием для действия:

```python
project = await session.get(Project, project_id)
if project is None:
    raise HTTPException(status_code=404, ...)
result = await project_workflow_service.decide_project(
    session, project, action=..., actor=reviewer   # reviewer проверен зависимостью require_project_reviewer
)
```

Этот паттерн одинаков во всех `app/api/v1/admin.py`, `leader.py`,
`projects.py` эндпоинтах, принимающих `{id}` в пути. Отдельно проверено:

- `GET /projects/questions` не перехватывается параметризованным
  `GET /projects/{project_id}` (порядок регистрации маршрутов важен —
  зафиксировано регрессионным тестом).
- `decide_task_application` в Leader Mode проверяет, что вызывающий —
  именно создатель конкретной задачи (`task.creator_id == actor.id`), а
  не просто "любой лидер".

## Известные ограничения матрицы

- Точечные `PermissionGrant` не имеют собственного UI управления в Mini
  App (только в боте, `admin_rights_block6.py`) — см.
  `docs/PRODUCTION_READINESS_AUDIT.md`.
- Нет отдельной роли "reviewer партнёрских предложений" — используется тот
  же грант `partners.manage`, что и для управления самими партнёрами/
  предложениями (создание/архивирование), т.е. более широкий, чем строго
  необходимо для одной лишь проверки заявок. Технически несложно разделить
  на `partners.manage` (CRUD) и `partners.review` (только заявки), если
  потребуется более гранулярный контроль — не сделано в этом блоке, чтобы
  не плодить права без реального запроса на них.
