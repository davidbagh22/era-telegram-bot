# Аудит кнопок и навигации бота ЭРА

Дата: 2026-07-10
Ветка: `audit-buttons-stability`
База: `main`

## Цель

Проверить reply-кнопки, inline-кнопки, команды и `callback_data`, найти безопасные навигационные проблемы и исправить только то, что не затрагивает регистрацию, БД, аукционы, мероприятия и активности.

## Проверенные точки входа

### Общая инициализация

- `app/bot.py` — порядок подключения роутеров.
- `app/handlers/start.py` — `/start`, `/menu`, `menu:main`, проверка подписки.
- `app/handlers/participant/__init__.py` — подключение пользовательских роутеров.
- `app/handlers/admin/__init__.py` — подключение админских роутеров.
- `app/handlers/leader/__init__.py` — подключение лидерских роутеров.

### Клавиатуры

- `app/keyboards/participant.py`
- `app/keyboards/admin.py`
- `app/keyboards/leader.py`
- `app/keyboards/common.py`
- `app/keyboards/registration.py`

### Основные обработчики

- `app/handlers/participant/navigation.py`
- `app/handlers/participant/cabinet.py`
- `app/handlers/participant/cabinet_hubs.py`
- `app/handlers/participant/task_block2.py`
- `app/handlers/participant/task_reply.py`
- `app/handlers/participant/task_flow.py`
- `app/handlers/participant/about.py`
- `app/handlers/participant/departments.py`
- `app/handlers/admin/panel.py`
- `app/handlers/admin/management_ready.py`
- `app/handlers/chat_binding.py`

## Reply-кнопки главного меню

| Кнопка | Обработчик | FSM | Статус |
|---|---|---:|---|
| `👤 Личный кабинет` | `participant/navigation.py::personal_cabinet_button` | очищается | OK |
| `📅 Афиша` | `participant/navigation.py::schedule_button` | очищается | OK |
| `✅ Задачи` | `participant/task_block2.py::tasks_reply_button` | очищается | исправлено/OK |
| `⭐ Возможности` | `participant/navigation.py::opportunities_button` | очищается | OK |
| `🏆 Рейтинг` | `participant/cabinet.py::rating_button` | очищается | OK |
| `💬 Связь` | `participant/navigation.py::contact_button` | очищается | OK |
| `⚙️ Панель` | `participant/navigation.py::panel_button` | очищается | OK, скрыта от обычного участника |
| `🧭 Главное меню` | `participant/navigation.py::main_menu_message` | очищается | OK |

## Команды

| Команда | Обработчик | FSM | Доступ |
|---|---|---:|---|
| `/start` | `start.py::start` | очищается | публичная/private |
| `/menu` | `start.py::start` | очищается | публичная/private |
| `/rules` | `start.py::private_rules` | очищается | private |
| `/about`, `/help` | `participant/about.py::about_button` | очищается | участник |
| `/journey` | `participant/cabinet.py::journey_button` | очищается | участник |
| `/rating` | `participant/cabinet.py::rating_button` | очищается | участник |
| `/tasks` | `participant/task_reply.py::tasks_command` | очищается | участник |
| `/team`, `/departments` | `participant/departments.py::departments_menu_button` | очищается | участник |
| `/admin` | `admin/panel.py::admin_command` | очищается | админ/права |
| `/panel` | `admin/management_ready.py::panel_command` | очищается | админ/права |
| `/bind` | `chat_binding.py::bind_current_chat` | не FSM-сценарий | только админ |

## Inline-кнопки главного уровня

| Callback | Назначение | Статус |
|---|---|---|
| `menu:main` | возврат в главное меню | OK, FSM очищается |
| `cabinet:open` | личный кабинет | OK |
| `events:list` | афиша | OK |
| `cabinet:tasks` | задачи | OK, есть дублирующие legacy handlers ниже |
| `rewards:menu` | возможности/награды | OK |
| `cabinet:rating` | рейтинг | OK |
| `contact:menu` | связь | OK |
| `panel:open` | панель лидера/админа | OK, обычному участнику не показывается |

## Найдено и исправлено

### 1. Дубли reply-обработчика `✅ Задачи`

Было:

- reply-кнопка `✅ Задачи` обрабатывалась отдельным shim-файлом `task_reply.py`;
- основной блок задач `task_block2.py` уже содержал всю клавиатуру и callback-логику задач.

Сделано:

- прямой reply-handler `✅ Задачи` перенесён в `task_block2.py` рядом с `cabinet:tasks`;
- `task_reply.py` оставлен только для команды `/tasks`;
- FSM очищается в обоих входах.

Затронутые файлы:

- `app/handlers/participant/task_block2.py`
- `app/handlers/participant/task_reply.py`

### 2. Неактивные кнопки портфолио

Было:

- `portfolio:view` — отдельный callback был избыточен: пользователь уже находится в портфолио;
- `portfolio:upload` — в текущей видимой навигации нет безопасного завершённого сценария загрузки достижения.

Сделано:

- из `portfolio_keyboard()` убраны нерабочие/no-op кнопки;
- оставлены рабочие действия: скачать резюме и вернуться в «Мои данные».

Затронутый файл:

- `app/keyboards/participant.py`

## Найдено, но не исправлено в этом PR

Эти пункты не тронуты, потому что требуют продуктового решения или затрагивают большие рабочие сценарии.

### 1. Legacy-дубли задач

Есть пересечения обработчиков между:

- `task_block2.py`
- `task_flow.py`
- `cabinet.py`

Повторяются callback-паттерны:

- `cabinet:tasks`
- `task:view:*`
- `task:result:*`
- `TaskSubmissionStates.result`

Фактически раньше срабатывает роутер, который подключён выше в `participant/__init__.py`, поэтому это не ломает текущую навигацию. Но это технический долг: позже лучше оставить один финальный task-flow и удалить legacy-дубли.

### 2. Дубли админских меню

`admin:menu:system` и `admin:menu:communications` есть в `management_ready.py` и также подпадают под общий обработчик `admin/panel.py::admin_submenu`.

Текущий порядок подключения делает `management_ready.py` приоритетным. Это работает, но лучше позже явно разделить старое и новое меню.

### 3. Командные handlers без кнопок

Есть handlers, которые не имеют отдельной кнопки, но это нормально:

- `/rules`
- `/about`
- `/help`
- `/team`
- `/departments`
- `/tasks`
- `/journey`
- `/rating`
- `/bind`

Это не баг: команды нужны для быстрого доступа, служебных сценариев или чатов.

## Проверка “назад”

| Раздел | Назад | Статус |
|---|---|---|
| Главное меню | `menu:main` | OK, FSM очищается |
| Связь | `contact:menu` / `menu:main` | OK |
| Команда/департаменты | `team:menu`, `departments:menu`, `contact:menu` | OK |
| Личный кабинет | `cabinet:open`, `cabinet:profile` | OK |
| Задачи | `cabinet:tasks`, `cabinet:open` | OK |
| Админка | `admin:panel`, `admin:menu:*` | OK |
| Управление | `admin:menu:system` | OK |
| Общение | `admin:menu:communications` | OK |

## FSM

Проверено:

- `/start` очищает FSM.
- `/menu` очищает FSM.
- `menu:main` очищает FSM.
- reply-кнопки главного меню очищают FSM.
- `/admin`, `/panel`, `/tasks` очищают FSM.

## Доступ обычного участника

Проверено по видимой логике:

- reply-кнопка `⚙️ Панель` добавляется только если пользователь privileged или admin;
- inline-кнопка `panel:open` добавляется только если пользователь privileged или admin;
- `panel:open` дополнительно проверяет роль/права;
- админские callback-и защищены `_guard()` в `admin/panel.py` и `admin/management_ready.py`;
- `/bind` доступен только администратору.

Обычный участник не должен видеть админские действия в главном меню и не должен получить доступ к ним при ручном callback/команде.

## Не трогалось

- регистрация;
- структура БД и миграции;
- аукцион;
- мероприятия;
- активности после мероприятий;
- бизнес-логика начислений;
- заявки и approve/reject сценарии.

## Проверки после PR

GitHub Actions должен выполнить:

```bash
python -m compileall -q app
python -m unittest discover -s tests -v
```

Workflow: `Bot checks`.
