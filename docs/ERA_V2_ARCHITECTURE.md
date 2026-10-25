# ERA Bot v2 — product and technical architecture

## Product purpose

ERA Bot is not a directory of commands. It is a guided operating system for a
community. It should help a new person join safely, discover where they belong,
participate in events, build projects, earn recognition and grow into a role with
more responsibility. For administrators and leaders it should turn scattered
Telegram activity into visible, manageable processes.

## Principles

1. Every screen answers three questions: where am I, what can I do, how do I go back.
2. Telegram reply buttons are the permanent navigation; inline buttons are local actions.
3. One message is edited while navigating whenever possible, to avoid chat clutter.
4. User-facing copy is warm, respectful and concise. We address the user as «Вы».
5. Internal codes, IDs and slash commands are never the primary interface.
6. Every long form saves progress after each answer and can be resumed.
7. Roles, offices and permissions are separate concepts.
8. Destructive actions are reversible by default and always audited.
9. Points are a real spendable balance: earning and spending are separate transactions.
10. Every process has a clear owner, status, deadline and next action.

## Current strengths

- The bot already has a working Telegram webhook, PostgreSQL, Redis FSM and scheduler.
- Users, applications, departments, events, projects, tasks, points, badges and
  portfolio items already exist as domain entities.
- There is an audit log and a safe notification layer.
- Event registration and staged reminders already provide a useful foundation.
- Role-based leader and administrator areas already exist.

## Current weaknesses

- Telegram commands are registered globally, but several handlers only work in group chats.
- The subscription gate silently disables itself when the channel ID is missing.
- Navigation is made of long inline lists and creates too many chat messages.
- Participant, leader and administrator workflows are implemented as large handler files.
- Project and event lifecycles are only loosely connected.
- Tasks support one assignee only and cannot represent a public challenge.
- Portfolio, certificates and badges are separate records without a unified review flow.
- Roles are used as both hierarchy and access control; offices are not modeled.
- There are no auctions, reward catalogue, granular permissions or saved audience filters.
- Administrator lists have no pagination, search or filter summaries.

## Navigation

Permanent participant keyboard:

- «Мой путь»
- «Мероприятия»
- «Проекты»
- «Рейтинг»
- «Команда ЭРА»
- «Задать вопрос»

Administrators additionally see «Управление». Leaders see «Панель лидера».
Every nested inline screen contains «Назад» and «Главное меню».

The Telegram command menu contains only commands that work in a private chat:
`/start`, `/menu`, `/journey`, `/events`, `/projects`, `/rating`, `/team`, `/rules`.

## Registration

Final questions:

1. first name and last name;
2. age;
3. phone and email;
4. city;
5. study or work;
6. current occupation;
7. department and directions of interest;
8. available time;
9. desired path: participant, activist, leader, department head, council;
10. motivation;
11. consent.

The experience question is removed. Subscription is verified before registration.
All non-administrator applications require approval.

## Identity model

- **Role** controls the broad interface: participant, activist, leader, head,
  council, administrator.
- **Participation status** describes progress and is independent from access.
- **Office** is a public title, for example Head of External Relations or Leader
  of Social Initiatives.
- **Permission** grants a specific action such as reviewing projects, managing an
  event, awarding points or sending a broadcast.

Offices can have start/end dates, public contacts and up to several holders. Changes
are audited. Only the chair/primary administrator can delegate administrative rights.

## Participant journey

«Мой путь» contains:

- current role, status and offices;
- spendable points balance and an explanation of rewards;
- departments, directions and direct chat buttons;
- combined activity: attended events and implemented projects;
- portfolio summary: certificates, badges, recommendations and achievements;
- the next useful action.

The old profile and separate department list are removed from the main flow.

## Projects

The constructor has six blocks and autosaves each answer:

1. Idea — formula, title.
2. Audience — portrait and real need.
3. Concept — scenario and differentiator.
4. Organisation — format, venue request, date, time, team, budget.
5. Marketing — channels, ten-day plan, announcement, participant reminder.
6. Sustainability — risks, success criteria and 48-hour follow-up.

Every difficult question includes an optional «ИИ-подсказка» containing a copyable
prompt. The bot does not call AI automatically. A participant can preview, edit,
download the Telegram document, keep a draft or submit it.

Lifecycle:

`draft → submitted → initial_review → venue_review → approved → in_progress → completed`

Alternative states: `needs_revision`, `postponed`, `rejected`, `cancelled`.
Administrator decisions always include a comment. Venue review sends up to five
reminders, with snooze options.

## Events

An approved project may become an event without re-entering data. Event cards show
title, date, time, venue, places, points and the participant's current status.

Lifecycle:

`draft → approval → published → registration_open → registration_closed → active → completed`

Participants receive confirmation and reminders. After completion an administrator
can create reward activities: feedback, selfie, video, file or free-text result.
Each activity has points/badge/certificate rewards and optional manual review.

## Tasks and challenges

- A private task has selected assignees.
- A challenge is published to a filtered audience and participants join voluntarily.
- Participants can see other joined members and the relevant department chat.
- Submission supports text, file, photo or video and lists collaborators.
- Administrator/leader reviews the result and distributes rewards individually.
- Assignees and owners receive deadline reminders.

## Points, badges and rewards

Points are recorded as immutable transactions. Spending creates a negative transaction.
Balances can never become negative.

Initial badge catalogue:

1. «Первый шаг» — completed registration.
2. «Голос ЭРА» — valuable community contribution.
3. «Надёжный участник» — consistent attendance and task completion.
4. «Командный игрок» — strong collaborative work.
5. «Организатор» — delivered an event.
6. «Проектный автор» — approved project.
7. «Медиа-двигатель» — content and promotion contribution.
8. «Амбассадор ЭРА» — brought people or partnerships.
9. «Наставник» — helped another participant grow.
10. «Прорыв месяца» — exceptional progress.

The reward catalogue has a fixed point cost. Auctions have an audience filter,
start/end time, minimum bid and bid step. Points are reserved while the auction is
active, released for non-winners and charged only after an administrator confirms a winner.

## Portfolio

Unified item types: ERA event, external event, project, badge, certificate,
recommendation, task result and office history. Participants may submit files for
review. Administrators may attach one shared document to an audience or individual
documents to selected users.

The bot generates a branded PDF resume containing verified items only. All files
remain available as Telegram documents.

## Administration

Main areas:

1. People — applications, participants, hierarchy, offices, permissions and archive.
2. Activity — projects, venue decisions, events, tasks/challenges and evidence.
3. Communication — questions, broadcasts and configurable chat greetings.
4. Growth — points, badges, rewards, auctions, portfolio and certificates.
5. Management — analytics, exports, settings and audit.

Lists are paginated. Filters can be combined and always show a human-readable summary.
People can be searched by first name, last name, Telegram username or Telegram ID.

## Leader area

Leaders see only their assigned departments/directions unless granted a broader
permission. They can:

- view and contact members in their scope;
- publish tasks and challenges to their scope;
- review task results if permitted;
- prepare projects and events;
- recommend a role, office, points or badge with a reason;
- request resources or venue approval;
- send a broadcast for administrator approval;
- see scoped analytics and overdue work.

Leaders cannot delete users, spend points, grant themselves rights or approve their
own project/event.

## Ten end-to-end validation cycles

1. Subscription, registration and application approval.
2. Permanent navigation and back paths for every participant screen.
3. Participant journey, points, chats and portfolio.
4. Project draft, resume, edit, submit and administrator review.
5. Venue review, snooze reminders and project-to-event conversion.
6. Event registration, confirmations, reminders and completion activities.
7. Private tasks, public challenges, team joining and result review.
8. Points, badges, reward catalogue and auction accounting.
9. Search, filters, offices, permissions, archive and leader boundaries.
10. Broadcast filters, greetings, PDF resume, Excel export and production smoke test.

Each cycle contains automated domain tests, handler tests and a short Telegram acceptance
checklist. No production data is deleted by migrations.
