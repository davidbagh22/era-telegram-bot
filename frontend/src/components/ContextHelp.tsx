import { useEffect, useMemo, useState } from "react";
import { BottomSheet } from "./BottomSheet";

export type ContextHelpMode = "user" | "admin" | "leader";

interface HelpTopic {
  key: string;
  title: string;
  intro: string;
  what: string;
  value: string;
  how: string;
  important?: string;
}

const TOPICS: Record<string, HelpTopic> = {
  home: {
    key: "home",
    title: "Главная — что делать здесь",
    intro: "Это ваш быстрый старт в ЭРА: только то, что важно сейчас.",
    what: "Посмотрите ближайшее событие, задачу, проект или следующий шаг развития.",
    value: "Вы не теряете возможности и сразу видите, куда лучше включиться сегодня.",
    how: "Нажимайте на карточку, чтобы открыть детали. Нижнее меню ведёт в основные разделы.",
  },
  projects: {
    key: "projects",
    title: "Проекты",
    intro: "Здесь идеи превращаются в реальные проекты и роли.",
    what: "Откройте проект, изучите цель, команду, этапы и доступные действия.",
    value: "Участие даёт практический опыт, результат для портфолио и путь к более сильным ролям.",
    how: "Выберите проект → посмотрите детали → присоединитесь или выполните доступное действие.",
  },
  project_detail: {
    key: "project_detail",
    title: "Карточка проекта",
    intro: "Вся логика проекта собрана в одном месте.",
    what: "Проверьте цель, сроки, команду, задачи и текущий статус.",
    value: "Вы понимаете, где проект сейчас и чем именно можете быть полезны.",
    how: "Используйте действия в карточке по порядку. Статусы обновляются по реальной работе команды.",
  },
  events: {
    key: "events",
    title: "События",
    intro: "Афиша ЭРА и ваша история участия.",
    what: "Выберите событие, прочитайте программу и зарегистрируйтесь, если хотите прийти.",
    value: "Вы заранее видите формат, место, время и что получите от участия.",
    how: "После регистрации следите за деталями в карточке. Если планы изменились — отмените участие заранее.",
  },
  event_detail: {
    key: "event_detail",
    title: "Карточка события",
    intro: "Здесь всё, что нужно до, во время и после мероприятия.",
    what: "Проверьте место, время, программу, чат и активности. Зарегистрируйтесь или управляйте своей записью.",
    value: "Подтверждённое участие может приносить баллы, результаты и записи в вашем пути ЭРА.",
    how: "На мероприятии используйте только официальный способ подтверждения присутствия, указанный в карточке.",
    important: "Баллы начисляются за подтверждённые действия, а не просто за нажатие «Я приду».",
  },
  activity: {
    key: "activity",
    title: "Моя активность",
    intro: "Задачи, календарь и история — это ваш рабочий след в ЭРА.",
    what: "Проверьте, что нужно сделать сейчас, какие сроки впереди и что уже завершено.",
    value: "Так формируется подтверждённый опыт, а не просто список посещений.",
    how: "Открывайте задачу → выполняйте условия → отправляйте результат через указанное действие.",
  },
  community: {
    key: "community",
    title: "Сообщество",
    intro: "Здесь собраны люди, возможности и механики участия вокруг ЭРА.",
    what: "Смотрите возможности, опросы, рейтинг и другие форматы, которые доступны вам сейчас.",
    value: "Раздел помогает быстрее находить людей, роли и следующие точки роста.",
    how: "Открывайте только то, что вам реально интересно; внутри каждой карточки есть условия и следующий шаг.",
  },
  opportunities: {
    key: "opportunities",
    title: "Возможности",
    intro: "Подборка реальных шансов: проекты, программы, роли и привилегии.",
    what: "Откройте возможность и проверьте условия, срок и требования.",
    value: "Активность в ЭРА превращается в доступ к новым форматам и опыту.",
    how: "Если подходите по условиям — действуйте из карточки. Не копите возможности «на потом».",
  },
  rewards: {
    key: "rewards",
    title: "Баллы и награды",
    intro: "Баллы показывают подтверждённую активность и открывают дополнительные возможности.",
    what: "Проверьте баланс, доступные награды и условия получения.",
    value: "Вы видите, во что превращается ваша реальная активность внутри системы.",
    how: "Баллы приходят автоматически за подтверждённые действия. Награды открывайте только через официальные кнопки раздела.",
  },
  surveys: {
    key: "surveys",
    title: "Опросы",
    intro: "Короткий способ влиять на то, что ЭРА делает дальше.",
    what: "Ответьте на открытые вопросы и выбирайте вариант, который действительно отражает ваше мнение.",
    value: "Команда получает живую обратную связь и может точнее собирать проекты и форматы.",
    how: "Откройте активный опрос → ответьте → отправьте. Повторно голосовать можно только если это разрешено самим опросом.",
  },
  profile: {
    key: "profile",
    title: "Профиль",
    intro: "Ваш путь, результаты и инструменты роста в одном месте.",
    what: "Проверьте баллы, уровень, портфолио, результаты, «Мой вектор» и приглашения друзей.",
    value: "Это ваша подтверждённая история внутри ЭРА — от участия до лидерских результатов.",
    how: "Открывайте нужный блок. В «Пригласить друга» вы получите личный код и ссылку для приглашения.",
  },
  progress: {
    key: "progress",
    title: "Мой прогресс",
    intro: "Показывает, как складывается ваш путь от участника к более активной роли.",
    what: "Посмотрите текущий уровень, выполненные действия и то, чего не хватает до следующего шага.",
    value: "Вы видите конкретный прогресс, а не абстрактную оценку.",
    how: "Используйте подсказки как навигацию: выберите один следующий шаг и выполните его в соответствующем разделе.",
  },
  development: {
    key: "development",
    title: "Мой вектор",
    intro: "Личный инструмент самоанализа. Это не оценка вашей ценности и не рейтинг ЭРА.",
    what: "Проходите короткую ежемесячную рефлексию, исследования и фиксируйте небольшой следующий шаг.",
    value: "Вы замечаете изменения в состоянии, сильные стороны и то, что стоит попробовать дальше.",
    how: "Отвечайте про себя, а не «как правильно». Результаты сравнивают вас прежде всего с вами самим.",
    important: "Личные заметки и психологические ответы не используются для рейтинга участников.",
  },
  development_checkin: {
    key: "development_checkin",
    title: "Ежемесячный check-in",
    intro: "Короткий снимок вашего текущего состояния.",
    what: "Ответьте на вопросы про последний период и выберите контекст, который реально на вас влиял.",
    value: "Система покажет изменение, одну точку поддержки и один небольшой эксперимент на месяц.",
    how: "Можно остановиться и продолжить позже. Отвечайте в своём темпе — здесь нет правильных ответов.",
  },
  development_library: {
    key: "development_library",
    title: "Исследования и история",
    intro: "Инструменты, которые помогают лучше понять устойчивые особенности и изменения во времени.",
    what: "Открывайте исследования тогда, когда есть интерес, и возвращайтесь к истории через несколько месяцев.",
    value: "Вы отделяете устойчивые особенности от временного состояния и видите динамику.",
    how: "Не нужно проходить всё сразу. Один осмысленный инструмент полезнее десяти быстрых тестов подряд.",
  },
  users: {
    key: "users",
    title: "Профиль участника",
    intro: "Публичная часть пути другого участника ЭРА.",
    what: "Посмотрите подтверждённые роли, результаты и активность, которые человек сделал доступными.",
    value: "Проще находить людей с подходящим опытом для проектов и команд.",
    how: "Используйте профиль как рабочий контекст, а не как повод сравнивать людей по одной цифре.",
  },
  admin: {
    key: "admin",
    title: "Панель администратора",
    intro: "Рабочее пространство для управления системой ЭРА.",
    what: "Открывайте нужный блок: люди, проекты, события, коммуникации, аналитика или настройки.",
    value: "Все управленческие решения собираются в одном месте и остаются контролируемыми.",
    how: "Сначала откройте объект и проверьте данные, затем выполняйте действие. Критичные операции имеют отдельные проверки и аудит.",
    important: "Не используйте административные данные для психологического рейтинга или не предусмотренной правилами оценки участников.",
  },
  admin_event: {
    key: "admin_event",
    title: "Управление событием",
    intro: "Полный цикл события: от публикации до подтверждённого результата.",
    what: "Проверьте программу, регистрацию, участников, активности, посещение и итоговые данные.",
    value: "Организатор видит реальную картину события и не ведёт параллельные списки вручную.",
    how: "Меняйте статус только по факту. Подтверждение посещения используйте как источник истины для баллов и статистики.",
  },
  admin_project: {
    key: "admin_project",
    title: "Проверка проекта",
    intro: "Здесь проект проходит управленческую проверку перед следующим этапом.",
    what: "Изучите цель, план, команду, сроки и материалы до принятия решения.",
    value: "Слабые места видны до запуска, а автор получает понятный следующий шаг.",
    how: "Не принимайте решение по одной карточке-метрике: откройте детали и оставьте содержательную обратную связь.",
  },
  leader: {
    key: "leader",
    title: "Пространство лидера",
    intro: "Рабочее место для управления командой и реальными задачами.",
    what: "Следите за проектами, участниками, задачами и тем, что требует вашего решения.",
    value: "Лидер видит не шум, а конкретные точки, где команда может застрять или вырасти.",
    how: "Работайте от приоритетов: сначала блокеры и сроки, затем развитие команды и новые инициативы.",
  },
};

function currentRoute(): string {
  const params = new URLSearchParams(window.location.search);
  const queryRoute = params.get("eraPath") || params.get("tgWebAppStartParam");
  if (queryRoute) {
    if (queryRoute.startsWith("event_")) return `events/${queryRoute.slice(6)}`;
    if (queryRoute.startsWith("project_")) return `projects/${queryRoute.slice(8)}`;
    if (queryRoute.startsWith("task_")) return `tasks/${queryRoute.slice(5)}`;
    return queryRoute.replace(/^\/?/, "").replace(/\/$/, "");
  }
  return window.location.hash.replace(/^#\/?/, "").replace(/\/$/, "") || "home";
}

function topicFor(mode: ContextHelpMode, route: string): HelpTopic {
  if (mode === "admin") {
    if (/^admin\/events\//.test(route)) return TOPICS.admin_event;
    if (/^admin\/projects\//.test(route)) return TOPICS.admin_project;
    return TOPICS.admin;
  }
  if (mode === "leader") return TOPICS.leader;

  if (/^projects\/\d+/.test(route)) return TOPICS.project_detail;
  if (route === "projects") return TOPICS.projects;
  if (/^events\/\d+/.test(route)) return TOPICS.event_detail;
  if (route === "events") return TOPICS.events;
  if (/^(tasks|calendar|history)(\/|$)/.test(route)) return TOPICS.activity;
  if (/^users\//.test(route)) return TOPICS.users;
  if (/^opportunities/.test(route)) return TOPICS.opportunities;
  if (/^(rewards|auctions)/.test(route)) return TOPICS.rewards;
  if (/^surveys/.test(route)) return TOPICS.surveys;
  if (/^(community|leaderboard)/.test(route)) return TOPICS.community;
  if (route === "profile") return TOPICS.profile;
  if (route === "progress") return TOPICS.progress;
  if (/^development\/checkin/.test(route)) return TOPICS.development_checkin;
  if (/^development\/(assessments|history|goals|privacy)/.test(route)) return TOPICS.development_library;
  if (/^development/.test(route)) return TOPICS.development;
  return TOPICS.home;
}

function seenKey(topic: HelpTopic): string {
  return `era_context_help_seen:${topic.key}:v1`;
}

function wasSeen(topic: HelpTopic): boolean {
  try {
    return window.localStorage.getItem(seenKey(topic)) === "1";
  } catch {
    return false;
  }
}

function markSeen(topic: HelpTopic): void {
  try {
    window.localStorage.setItem(seenKey(topic), "1");
  } catch {
    // Storage can be unavailable in private/embedded modes; help still works.
  }
}

export function ContextHelp({ mode }: { mode: ContextHelpMode }) {
  const [route, setRoute] = useState(() => currentRoute());
  const [open, setOpen] = useState(false);
  const topic = useMemo(() => topicFor(mode, route), [mode, route]);
  const [showCoach, setShowCoach] = useState(() => !wasSeen(topic));

  useEffect(() => {
    const sync = () => setRoute(currentRoute());
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);

  useEffect(() => {
    setOpen(false);
    setShowCoach(!wasSeen(topic));
  }, [topic]);

  const openHelp = () => {
    markSeen(topic);
    setShowCoach(false);
    setOpen(true);
  };

  // Participant and admin workspaces both have a persistent bottom navigation.
  // Keep the help affordance above it so it never intercepts navigation taps.
  const bottom = mode === "leader"
    ? "calc(1rem + env(safe-area-inset-bottom, 0px))"
    : "calc(5.5rem + env(safe-area-inset-bottom, 0px))";

  return (
    <>
      <div style={{ position: "fixed", right: "0.75rem", bottom, zIndex: 35, display: "flex", alignItems: "center", gap: "0.5rem", pointerEvents: "none" }}>
        {showCoach && (
          <button
            type="button"
            onClick={openHelp}
            style={{
              pointerEvents: "auto",
              borderRadius: "999px",
              padding: "0.52rem 0.72rem",
              border: "1px solid var(--era-border)",
              background: "color-mix(in srgb, var(--era-surface) 92%, transparent)",
              color: "var(--era-text)",
              boxShadow: "var(--era-shadow-card)",
              backdropFilter: "blur(16px)",
              fontSize: "var(--era-text-xs)",
              fontWeight: 800,
              whiteSpace: "nowrap",
            }}
          >
            Что здесь?
          </button>
        )}
        <button
          type="button"
          onClick={openHelp}
          aria-label={`Как пользоваться разделом: ${topic.title}`}
          style={{
            pointerEvents: "auto",
            width: 42,
            height: 42,
            borderRadius: "50%",
            padding: 0,
            border: "1px solid color-mix(in srgb, var(--era-red) 45%, var(--era-border))",
            background: "color-mix(in srgb, var(--era-surface) 90%, transparent)",
            color: "var(--era-text)",
            boxShadow: "var(--era-shadow-card)",
            backdropFilter: "blur(16px)",
            display: "grid",
            placeItems: "center",
            fontFamily: "var(--era-font-display)",
            fontSize: "1rem",
            fontWeight: 900,
          }}
        >
          i
        </button>
      </div>

      <BottomSheet open={open} onClose={() => setOpen(false)} title={topic.title}>
        <p style={{ margin: "0 0 1rem", color: "var(--era-text-muted)", lineHeight: 1.5 }}>{topic.intro}</p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
          {[
            ["Что делать", topic.what],
            ["Что это даст", topic.value],
            ["Как пользоваться", topic.how],
          ].map(([label, text]) => (
            <div key={label} style={{ padding: "0.8rem", borderRadius: "var(--era-radius-card)", background: "var(--era-surface-2)", border: "1px solid var(--era-border)" }}>
              <strong style={{ display: "block", marginBottom: "0.25rem", fontSize: "var(--era-text-sm)" }}>{label}</strong>
              <p style={{ margin: 0, color: "var(--era-text-muted)", lineHeight: 1.5, fontSize: "var(--era-text-sm)" }}>{text}</p>
            </div>
          ))}
          {topic.important && (
            <div style={{ padding: "0.8rem", borderRadius: "var(--era-radius-card)", background: "var(--era-tint-red)", border: "1px solid color-mix(in srgb, var(--era-red) 25%, transparent)" }}>
              <strong style={{ display: "block", marginBottom: "0.25rem", fontSize: "var(--era-text-sm)" }}>Важно</strong>
              <p style={{ margin: 0, lineHeight: 1.5, fontSize: "var(--era-text-sm)" }}>{topic.important}</p>
            </div>
          )}
        </div>
      </BottomSheet>
    </>
  );
}
