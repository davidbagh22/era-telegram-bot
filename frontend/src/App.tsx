import {
  ArrowLeft,
  ArrowRight,
  Award,
  Bell,
  BriefcaseBusiness,
  CalendarDays,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  FolderKanban,
  Home,
  ListTodo,
  LoaderCircle,
  MapPin,
  MessageCircle,
  Plus,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  Trophy,
  UserRound,
  UsersRound,
  X
} from "lucide-react";
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, haptic, initializeTelegram } from "./api";
import { BrandLogo } from "./components/BrandLogo";
import type {
  DashboardData,
  EraUser,
  EventItem,
  PortfolioItem,
  ProjectItem,
  RatingItem,
  SessionResponse,
  TaskItem
} from "./types";

type Tab = "home" | "events" | "projects" | "profile";

const internalDirections = ["Лидерство", "Культура", "Интерактив"];
const externalDirections = ["Международное направление", "Медиа", "Социальные инициативы"];
const skillOptions = [
  "Организация мероприятий",
  "Фото / видео",
  "Дизайн",
  "Тексты",
  "SMM",
  "Публичные выступления",
  "Волонтёрство",
  "Коммуникации",
  "Международные проекты",
  "Работа с людьми"
];

const projectStatusLabels: Record<string, string> = {
  draft: "Черновик",
  pending_review: "На рассмотрении",
  needs_revision: "Нужна доработка",
  approved: "Одобрен",
  in_progress: "В работе",
  completed: "Завершён",
  rejected: "Не одобрен"
};

const taskStatusLabels: Record<string, string> = {
  new: "Новая",
  in_progress: "В работе",
  review: "На проверке",
  completed: "Выполнена",
  overdue: "Просрочена",
  cancelled: "Отменена"
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" }).format(
    new Date(`${value}T12:00:00`)
  );
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export function App() {
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSession(await api<SessionResponse>("/api/session"));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Не удалось открыть приложение."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    initializeTelegram();
    void loadSession();
  }, [loadSession]);

  if (loading) return <LaunchScreen />;
  if (error || !session) {
    return (
      <CenteredState
        icon={<CircleAlert size={28} />}
        title="Не удалось открыть ЭРА"
        text={error || "Попробуйте открыть приложение ещё раз."}
        action={<button className="button button--primary" onClick={loadSession}>Повторить</button>}
      />
    );
  }
  if (session.state === "needs_registration") {
    return <RegistrationWizard session={session} onComplete={loadSession} />;
  }
  if (session.state !== "ready" || !session.user) {
    const rejected = session.state === "rejected";
    return (
      <CenteredState
        icon={rejected ? <CircleAlert size={28} /> : <Clock3 size={28} />}
        title={rejected ? "Заявка не одобрена" : "Анкета на рассмотрении"}
        text={
          rejected
            ? "Вы можете уточнить решение у команды ЭРА через бота."
            : "Команда ЭРА проверит анкету. После подтверждения здесь откроется Ваш личный кабинет."
        }
        action={<button className="button button--soft" onClick={loadSession}>Проверить статус</button>}
      />
    );
  }
  return <AppShell user={session.user} onSessionRefresh={loadSession} />;
}

function LaunchScreen() {
  return (
    <main className="launch-screen">
      <div className="launch-glow launch-glow--one" />
      <div className="launch-glow launch-glow--two" />
      <BrandLogo size="large" />
      <div className="loader-line"><span /></div>
      <p>Открываем Вашу ЭРА</p>
    </main>
  );
}

function CenteredState({
  icon,
  title,
  text,
  action
}: {
  icon: ReactNode;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <main className="centered-state page-shell">
      <BrandLogo size="large" />
      <div className="state-icon">{icon}</div>
      <h1>{title}</h1>
      <p>{text}</p>
      {action}
    </main>
  );
}

function AppShell({ user, onSessionRefresh }: { user: EraUser; onSessionRefresh: () => void }) {
  const [tab, setTab] = useState<Tab>("home");
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (text: string) => {
    setToast(text);
    window.setTimeout(() => setToast(null), 2800);
  };

  return (
    <div className="app-frame">
      <header className="app-header">
        <BrandLogo />
        <button className="icon-button" aria-label="Уведомления" onClick={() => showToast("Новые уведомления приходят через бот ЭРА")}>
          <Bell size={20} />
          <span className="notification-dot" />
        </button>
      </header>
      <main className="app-content">
        {tab === "home" && <HomeScreen user={user} setTab={setTab} showToast={showToast} />}
        {tab === "events" && <EventsScreen showToast={showToast} />}
        {tab === "projects" && <ProjectsScreen showToast={showToast} />}
        {tab === "profile" && (
          <ProfileScreen user={user} showToast={showToast} refreshSession={onSessionRefresh} />
        )}
      </main>
      <BottomNavigation current={tab} onChange={setTab} />
      {toast && <div className="toast"><Check size={17} />{toast}</div>}
    </div>
  );
}

function BottomNavigation({ current, onChange }: { current: Tab; onChange: (tab: Tab) => void }) {
  const items: Array<{ id: Tab; label: string; icon: ReactNode }> = [
    { id: "home", label: "Главная", icon: <Home size={21} /> },
    { id: "events", label: "События", icon: <CalendarDays size={21} /> },
    { id: "projects", label: "Проекты", icon: <FolderKanban size={21} /> },
    { id: "profile", label: "Профиль", icon: <UserRound size={21} /> }
  ];
  return (
    <nav className="bottom-nav" aria-label="Основная навигация">
      {items.map((item) => (
        <button
          key={item.id}
          className={current === item.id ? "bottom-nav__item is-active" : "bottom-nav__item"}
          onClick={() => {
            haptic.tap();
            onChange(item.id);
          }}
        >
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </nav>
  );
}

function HomeScreen({
  user,
  setTab,
  showToast
}: {
  user: EraUser;
  setTab: (tab: Tab) => void;
  showToast: (text: string) => void;
}) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<DashboardData>("/api/dashboard")
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="screen screen--home">
      <section className="welcome-row">
        <div>
          <p className="eyebrow">Личный кабинет</p>
          <h1>Здравствуйте, {user.first_name}</h1>
          <p>Продолжайте свой путь в ЭРА.</p>
        </div>
        <div className="avatar">{user.first_name.slice(0, 1).toUpperCase()}</div>
      </section>

      <section className="journey-card">
        <div className="journey-card__glow" />
        <div className="journey-card__top">
          <div>
            <span className="mini-label">Ваш статус</span>
            <h2>{user.status_label}</h2>
          </div>
          <span className="status-pill">{user.role_label}</span>
        </div>
        <p>Каждое действие становится опытом, достижением и частью Вашего портфолио.</p>
        <div className="journey-progress"><span style={{ width: `${Math.min(92, 18 + user.stats.events * 9 + user.stats.projects * 12)}%` }} /></div>
        <button className="text-action" onClick={() => setTab("profile")}>Посмотреть мой путь <ArrowRight size={16} /></button>
      </section>

      <section className="stats-grid">
        <StatCard icon={<Sparkles size={19} />} value={user.stats.points} label="Баллов" tone="red" />
        <StatCard icon={<Trophy size={19} />} value={data?.rating_place ? `#${data.rating_place}` : "—"} label="В рейтинге" tone="purple" />
        <StatCard icon={<CalendarDays size={19} />} value={user.stats.events} label="Мероприятий" tone="pink" />
        <StatCard icon={<FolderKanban size={19} />} value={user.stats.projects} label="Проектов" tone="violet" />
      </section>

      <SectionHeader title="Быстрый старт" />
      <section className="quick-grid">
        <QuickAction icon={<CalendarDays />} title="Найти событие" text="Выберите ближайшее мероприятие" onClick={() => setTab("events")} />
        <QuickAction icon={<Target />} title="Создать проект" text="Оформите идею вместе с ИИ" onClick={() => setTab("projects")} featured />
        <QuickAction icon={<UsersRound />} title="Направления" text="Найдите своё место в команде" onClick={() => setTab("profile")} />
        <QuickAction icon={<MessageCircle />} title="Задать вопрос" text="Напишите команде ЭРА" onClick={() => {
          setTab("profile");
          showToast("Раздел вопросов находится в профиле");
        }} />
      </section>

      <SectionHeader title="Ближайшие мероприятия" action="Все" onAction={() => setTab("events")} />
      {loading ? <CardSkeleton /> : data?.upcoming_events.length ? (
        <div className="horizontal-list">
          {data.upcoming_events.map((event) => (
            <article className="event-preview" key={event.id}>
              <div className="date-tile"><strong>{new Date(`${event.date}T12:00:00`).getDate()}</strong><span>{new Intl.DateTimeFormat("ru-RU", { month: "short" }).format(new Date(`${event.date}T12:00:00`))}</span></div>
              <div><h3>{event.title}</h3><p><Clock3 size={14} />{event.time} · {event.location}</p></div>
              <span className="points-badge">+{event.points}</span>
            </article>
          ))}
        </div>
      ) : <EmptyInline text="Новые мероприятия скоро появятся." />}

      {data?.active_tasks.length ? (
        <>
          <SectionHeader title="Мои задачи" action="Профиль" onAction={() => setTab("profile")} />
          <div className="stack-list">
            {data.active_tasks.map((task) => (
              <article className="task-row" key={task.id}>
                <div className="task-check"><ListTodo size={18} /></div>
                <div><h3>{task.title}</h3><p>до {formatDateTime(task.deadline)}</p></div>
                <ChevronRight size={18} />
              </article>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

function StatCard({ icon, value, label, tone }: { icon: ReactNode; value: number | string; label: string; tone: string }) {
  return <article className={`stat-card stat-card--${tone}`}><div>{icon}</div><strong>{value}</strong><span>{label}</span></article>;
}

function QuickAction({ icon, title, text, onClick, featured = false }: { icon: ReactNode; title: string; text: string; onClick: () => void; featured?: boolean }) {
  return <button className={featured ? "quick-card quick-card--featured" : "quick-card"} onClick={() => { haptic.tap(); onClick(); }}><span className="quick-card__icon">{icon}</span><strong>{title}</strong><small>{text}</small><ArrowRight size={17} /></button>;
}

function SectionHeader({ title, action, onAction }: { title: string; action?: string; onAction?: () => void }) {
  return <div className="section-header"><h2>{title}</h2>{action && <button onClick={onAction}>{action}<ChevronRight size={15} /></button>}</div>;
}

function EventsScreen({ showToast }: { showToast: (text: string) => void }) {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState<number | null>(null);
  const [filter, setFilter] = useState<"all" | "registered">("all");

  const loadEvents = useCallback(() => {
    setLoading(true);
    api<EventItem[]>("/api/events").then(setEvents).finally(() => setLoading(false));
  }, []);

  useEffect(loadEvents, [loadEvents]);
  const visible = filter === "registered" ? events.filter((event) => event.registration_status) : events;

  const join = async (eventId: number) => {
    setJoining(eventId);
    try {
      await api(`/api/events/${eventId}/register`, { method: "POST" });
      haptic.success();
      showToast("Вы зарегистрированы на мероприятие");
      loadEvents();
    } catch (error) {
      haptic.error();
      showToast(error instanceof Error ? error.message : "Не удалось зарегистрироваться");
    } finally {
      setJoining(null);
    }
  };

  return (
    <div className="screen">
      <PageTitle eyebrow="Жизнь сообщества" title="Мероприятия" text="Выбирайте события, участвуйте и собирайте опыт в портфолио." />
      <div className="segmented"><button className={filter === "all" ? "is-active" : ""} onClick={() => setFilter("all")}>Все</button><button className={filter === "registered" ? "is-active" : ""} onClick={() => setFilter("registered")}>Мои регистрации</button></div>
      {loading ? <><CardSkeleton /><CardSkeleton /></> : visible.length ? (
        <div className="event-list">
          {visible.map((event) => (
            <article className="event-card" key={event.id}>
              <div className="event-card__accent" />
              <div className="event-card__meta"><span><CalendarDays size={15} />{formatDate(event.date)}</span><span>{event.time}</span><span className="points-badge">+{event.points}</span></div>
              <h2>{event.title}</h2>
              <p>{event.description}</p>
              <div className="event-card__details"><span><MapPin size={15} />{event.location}</span><span><UsersRound size={15} />{event.available_places === "без ограничений" ? "Без лимита" : `${event.available_places} мест`}</span></div>
              <button className={event.registration_status ? "button button--success" : "button button--primary"} disabled={Boolean(event.registration_status) || joining === event.id} onClick={() => join(event.id)}>{joining === event.id ? <LoaderCircle className="spin" size={18} /> : event.registration_status ? <><Check size={18} />Вы зарегистрированы</> : <>Зарегистрироваться<ArrowRight size={18} /></>}</button>
            </article>
          ))}
        </div>
      ) : <EmptyState icon={<CalendarDays />} title="Здесь пока пусто" text={filter === "registered" ? "Вы ещё не зарегистрированы на мероприятия." : "Новые мероприятия скоро появятся."} />}
    </div>
  );
}

function ProjectsScreen({ showToast }: { showToast: (text: string) => void }) {
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [wizard, setWizard] = useState(false);
  const [selected, setSelected] = useState<ProjectItem | null>(null);

  const loadProjects = useCallback(() => {
    setLoading(true);
    api<ProjectItem[]>("/api/projects").then(setProjects).finally(() => setLoading(false));
  }, []);
  useEffect(loadProjects, [loadProjects]);

  return (
    <div className="screen">
      <PageTitle eyebrow="От идеи к результату" title="Мои проекты" text="ИИ-конструктор поможет превратить идею в понятный проектный документ." />
      <button className="create-project-card" onClick={() => setWizard(true)}><span><Sparkles size={25} /></span><div><strong>Создать проект с ИИ</strong><small>Пошагово соберите идею, аудиторию, программу и результат</small></div><Plus size={22} /></button>
      <SectionHeader title="Ваши проекты" />
      {loading ? <CardSkeleton /> : projects.length ? (
        <div className="project-list">
          {projects.map((project) => (
            <button className="project-card" key={project.id} onClick={() => setSelected(project)}>
              <div className="project-card__icon"><FolderKanban size={20} /></div>
              <div><span className={`status-tag status-tag--${project.status}`}>{projectStatusLabels[project.status] || project.status}</span><h3>{project.title}</h3><p>{project.description}</p></div>
              <ChevronRight size={18} />
            </button>
          ))}
        </div>
      ) : <EmptyState icon={<FolderKanban />} title="Первый проект начинается с идеи" text="Не нужно писать идеально. Конструктор поможет собрать сильную структуру." action={<button className="button button--soft" onClick={() => setWizard(true)}>Начать проект</button>} />}
      {wizard && <ProjectWizard onClose={() => setWizard(false)} onCreated={(project) => { setWizard(false); loadProjects(); showToast("Проект сохранён"); setSelected(project); }} />}
      {selected && <ProjectDetails project={selected} onClose={() => setSelected(null)} onSubmitted={() => { setSelected(null); loadProjects(); showToast("Проект отправлен на рассмотрение"); }} />}
    </div>
  );
}

function ProjectWizard({ onClose, onCreated }: { onClose: () => void; onCreated: (project: ProjectItem) => void }) {
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    idea: "", department: "Внутренние связи", direction: "Лидерство", target_audience: "",
    relevance: "", goal: "", format: "Встреча", program: "", resources: "", team: "",
    expected_result: "", needs_from_era: "", use_ai: true
  });
  const steps = ["Идея", "Для кого", "Как устроено", "Результат"];
  const set = (key: keyof typeof form, value: string | boolean) => setForm((current) => ({ ...current, [key]: value }));
  const directions = form.department === "Внутренние связи" ? internalDirections : externalDirections;

  const canContinue = useMemo(() => {
    if (step === 0) return form.idea.trim().length >= 3;
    if (step === 1) return form.target_audience.trim() && form.relevance.trim() && form.goal.trim();
    if (step === 2) return form.program.trim() && form.resources.trim() && form.team.trim();
    return form.expected_result.trim() && form.needs_from_era.trim();
  }, [form, step]);

  const submit = async () => {
    setSaving(true); setError(null);
    try {
      const result = await api<{ id: number; title: string; status: string; document: string }>("/api/projects", { method: "POST", body: JSON.stringify(form) });
      haptic.success();
      onCreated({ id: result.id, title: result.title, status: result.status, document: result.document, description: form.idea, created_at: new Date().toISOString() });
    } catch (requestError) {
      haptic.error();
      setError(requestError instanceof Error ? requestError.message : "Не удалось создать проект.");
    } finally { setSaving(false); }
  };

  return (
    <Modal title="Проектный конструктор" onClose={onClose} full>
      <div className="wizard-progress">{steps.map((label, index) => <div key={label} className={index <= step ? "is-active" : ""}><span>{index < step ? <Check size={13} /> : index + 1}</span><small>{label}</small></div>)}</div>
      {step === 0 && <div className="form-stack"><FormIntro icon={<Sparkles />} title="Начнём с идеи" text="Объясните простыми словами, что Вы хотите создать. ИИ поможет оформить структуру." /><Field label="Идея проекта"><textarea rows={5} value={form.idea} onChange={(event) => set("idea", event.target.value)} placeholder="Например: провести культурный квест для новых участников ЭРА" /></Field><Field label="Департамент"><ChoiceGrid values={["Внутренние связи", "Внешние связи"]} selected={[form.department]} onToggle={(value) => { set("department", value); set("direction", value === "Внутренние связи" ? "Лидерство" : "Медиа"); }} /></Field><Field label="Направление"><ChoiceGrid values={directions} selected={[form.direction]} onToggle={(value) => set("direction", value)} /></Field></div>}
      {step === 1 && <div className="form-stack"><FormIntro icon={<UsersRound />} title="Определим смысл" text="Сильный проект понимает, для кого он создан и какую потребность закрывает." /><Field label="Целевая аудитория"><input value={form.target_audience} onChange={(event) => set("target_audience", event.target.value)} placeholder="Новые участники, студенты, команда ЭРА" /></Field><Field label="Почему проект нужен"><textarea rows={4} value={form.relevance} onChange={(event) => set("relevance", event.target.value)} placeholder="Какую проблему или потребность решает проект?" /></Field><Field label="Цель"><textarea rows={3} value={form.goal} onChange={(event) => set("goal", event.target.value)} placeholder="Что должно измениться после проекта?" /></Field></div>}
      {step === 2 && <div className="form-stack"><FormIntro icon={<BriefcaseBusiness />} title="Соберём реализацию" text="Теперь превратим идею в последовательность действий." /><Field label="Формат"><ChoiceGrid values={["Встреча", "Мастер-класс", "Игра", "Квест", "Дебаты", "Медиа-проект", "Волонтёрская акция", "Форум"]} selected={[form.format]} onToggle={(value) => set("format", value)} /></Field><Field label="Программа"><textarea rows={4} value={form.program} onChange={(event) => set("program", event.target.value)} placeholder="Открытие, основная часть, интерактив, финал" /></Field><Field label="Ресурсы"><textarea rows={3} value={form.resources} onChange={(event) => set("resources", event.target.value)} placeholder="Площадка, техника, материалы, партнёры" /></Field><Field label="Команда"><textarea rows={3} value={form.team} onChange={(event) => set("team", event.target.value)} placeholder="Координатор, ведущий, дизайнер, волонтёры" /></Field></div>}
      {step === 3 && <div className="form-stack"><FormIntro icon={<Target />} title="Зафиксируем результат" text="Результат должен быть понятным и измеримым." /><Field label="Ожидаемый результат"><textarea rows={4} value={form.expected_result} onChange={(event) => set("expected_result", event.target.value)} placeholder="Например: 30 участников, новая команда, фотоотчёт" /></Field><Field label="Какая поддержка нужна от ЭРА"><textarea rows={4} value={form.needs_from_era} onChange={(event) => set("needs_from_era", event.target.value)} placeholder="Команда, площадка, медиа, партнёры" /></Field><label className="toggle-row"><span><strong>Усилить проект с ИИ</strong><small>ИИ оформит ответы в полноценный документ</small></span><input type="checkbox" checked={form.use_ai} onChange={(event) => set("use_ai", event.target.checked)} /></label>{error && <p className="form-error">{error}</p>}</div>}
      <div className="modal-actions">{step > 0 && <button className="button button--ghost" onClick={() => setStep((current) => current - 1)}><ArrowLeft size={18} />Назад</button>}<button className="button button--primary" disabled={!canContinue || saving} onClick={() => step < steps.length - 1 ? setStep((current) => current + 1) : void submit()}>{saving ? <><LoaderCircle className="spin" size={18} />Формируем проект</> : step < steps.length - 1 ? <>Продолжить<ArrowRight size={18} /></> : <><Sparkles size={18} />Создать проект</>}</button></div>
    </Modal>
  );
}

function ProjectDetails({ project, onClose, onSubmitted }: { project: ProjectItem; onClose: () => void; onSubmitted: () => void }) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setSending(true); setError(null);
    try { await api(`/api/projects/${project.id}/submit`, { method: "POST" }); haptic.success(); onSubmitted(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Не удалось отправить проект."); }
    finally { setSending(false); }
  };
  return <Modal title={project.title} onClose={onClose} full><span className={`status-tag status-tag--${project.status}`}>{projectStatusLabels[project.status] || project.status}</span><div className="project-document">{project.document || project.description}</div>{error && <p className="form-error">{error}</p>}{["draft", "needs_revision"].includes(project.status) && <div className="modal-actions"><button className="button button--primary" onClick={submit} disabled={sending}>{sending ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}Отправить на рассмотрение</button></div>}</Modal>;
}

function ProfileScreen({ user, showToast, refreshSession }: { user: EraUser; showToast: (text: string) => void; refreshSession: () => void }) {
  const [section, setSection] = useState<"overview" | "portfolio" | "rating" | "tasks">("overview");
  const [portfolio, setPortfolio] = useState<PortfolioItem[]>([]);
  const [rating, setRating] = useState<RatingItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [departments, setDepartments] = useState<{ items: Array<{ name: string; directions: string[]; selected: boolean }>; selected_directions: string[] } | null>(null);
  const [admin, setAdmin] = useState<Record<string, number> | null>(null);
  const [question, setQuestion] = useState(false);

  useEffect(() => {
    void Promise.all([
      api<PortfolioItem[]>("/api/portfolio").then(setPortfolio),
      api<{ items: RatingItem[] }>("/api/rating").then((value) => setRating(value.items)),
      api<TaskItem[]>("/api/tasks").then(setTasks),
      api<typeof departments>("/api/departments").then(setDepartments)
    ]);
    if (user.is_admin) void api<Record<string, number>>("/api/admin/summary").then(setAdmin);
  }, [user.is_admin]);

  const updateTask = async (task: TaskItem) => {
    const next = task.status === "new" ? "in_progress" : "review";
    try {
      await api(`/api/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify({ status: next }) });
      setTasks((items) => items.map((item) => item.id === task.id ? { ...item, status: next } : item));
      showToast(next === "review" ? "Задача отправлена на проверку" : "Задача начата");
    } catch (error) { showToast(error instanceof Error ? error.message : "Не удалось изменить задачу"); }
  };

  return (
    <div className="screen">
      <section className="profile-hero"><div className="profile-avatar">{user.first_name[0]}</div><div><p>{user.role_label}</p><h1>{user.first_name} {user.last_name}</h1><span>{user.status_label}</span></div></section>
      <div className="profile-tabs"><button className={section === "overview" ? "is-active" : ""} onClick={() => setSection("overview")}>Обзор</button><button className={section === "portfolio" ? "is-active" : ""} onClick={() => setSection("portfolio")}>Портфолио</button><button className={section === "rating" ? "is-active" : ""} onClick={() => setSection("rating")}>Рейтинг</button><button className={section === "tasks" ? "is-active" : ""} onClick={() => setSection("tasks")}>Задачи</button></div>
      {section === "overview" && <div className="profile-section"><section className="identity-card"><div><span>Статус участия</span><strong>{user.status_label}</strong></div><div><span>Город</span><strong>{user.city || "Не указан"}</strong></div><div><span>Учёба / работа</span><strong>{user.education_work || "Не указано"}</strong></div></section><SectionHeader title="Мои направления" />{departments?.items.map((department) => <article className={department.selected ? "department-card is-selected" : "department-card"} key={department.name}><div><strong>{department.name}</strong><p>{department.directions.join(" · ")}</p></div>{department.selected && <span><Check size={14} />Выбрано</span>}</article>)}{user.is_admin && admin && <><SectionHeader title="Управление ЭРА" /><section className="admin-card"><div className="admin-card__head"><span><ShieldCheck size={20} /></span><div><strong>Панель администратора</strong><small>Сводка системы</small></div></div><div className="admin-metrics"><div><strong>{admin.participants}</strong><span>Участников</span></div><div><strong>{admin.pending_applications}</strong><span>Заявок</span></div><div><strong>{admin.pending_projects}</strong><span>Проектов</span></div><div><strong>{admin.upcoming_events}</strong><span>Событий</span></div></div><p>Решения по заявкам, ролям и баллам пока доступны через панель администратора в боте.</p></section></>}<button className="support-button" onClick={() => setQuestion(true)}><span><MessageCircle size={21} /></span><div><strong>Задать вопрос команде</strong><small>Ответ придёт через бот ЭРА</small></div><ChevronRight size={18} /></button><button className="refresh-link" onClick={refreshSession}>Обновить данные кабинета</button></div>}
      {section === "portfolio" && <div className="profile-section"><div className="portfolio-intro"><Award size={24} /><div><strong>Ваша история роста</strong><p>Здесь собираются проекты, мероприятия, задачи и достижения.</p></div></div>{portfolio.length ? portfolio.map((item) => <article className="portfolio-card" key={item.id}><span><Award size={18} /></span><div><strong>{item.title}</strong><small>{item.description || item.type}</small></div></article>) : <EmptyState icon={<Award />} title="Портфолио пока пустое" text="Оно начнёт заполняться после участия в мероприятиях, задачах и проектах." />}</div>}
      {section === "rating" && <div className="profile-section"><div className="rating-banner"><Trophy size={26} /><div><strong>Рейтинг вклада</strong><p>Не соревнование ради цифр, а отражение движения и ответственности.</p></div></div><div className="rating-list">{rating.map((item) => <article className={item.is_current_user ? "rating-row is-current" : "rating-row"} key={item.place}><span className="rating-place">{item.place <= 3 ? ["I", "II", "III"][item.place - 1] : item.place}</span><div className="rating-avatar">{item.name[0]}</div><strong>{item.name}</strong><b>{item.points}</b></article>)}</div></div>}
      {section === "tasks" && <div className="profile-section">{tasks.length ? tasks.map((task) => <article className="task-card" key={task.id}><div className="task-card__head"><span><ListTodo size={18} /></span><div><strong>{task.title}</strong><small>{taskStatusLabels[task.status] || task.status}</small></div><b>+{task.points}</b></div><p>{task.description}</p><div className="task-card__footer"><span><Clock3 size={14} />{formatDateTime(task.deadline)}</span>{["new", "in_progress"].includes(task.status) && <button onClick={() => updateTask(task)}>{task.status === "new" ? "Начать" : "На проверку"}<ArrowRight size={14} /></button>}</div></article>) : <EmptyState icon={<ListTodo />} title="Активных задач нет" text="Когда лидер назначит задачу, она появится здесь." />}</div>}
      {question && <QuestionModal onClose={() => setQuestion(false)} onSent={() => { setQuestion(false); showToast("Вопрос отправлен команде ЭРА"); }} />}
    </div>
  );
}

function QuestionModal({ onClose, onSent }: { onClose: () => void; onSent: () => void }) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setSending(true);
    try { await api("/api/questions", { method: "POST", body: JSON.stringify({ text }) }); haptic.success(); onSent(); }
    finally { setSending(false); }
  };
  return <Modal title="Вопрос команде ЭРА" onClose={onClose}><form className="form-stack" onSubmit={submit}><p className="modal-lead">Напишите коротко и понятно. Ответ придёт в личный чат с ботом.</p><Field label="Ваш вопрос"><textarea rows={6} value={text} onChange={(event) => setText(event.target.value)} placeholder="Что Вы хотите уточнить?" /></Field><button className="button button--primary" disabled={text.trim().length < 3 || sending}>{sending ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}Отправить</button></form></Modal>;
}

function RegistrationWizard({ session, onComplete }: { session: SessionResponse; onComplete: () => void }) {
  const telegramUser = session.telegram_user;
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    first_name: telegramUser.first_name || "", last_name: telegramUser.last_name || "", age: "", phone: "", city: "",
    education_work: "", occupation: "", departments: [] as string[], directions: [] as string[], available_time: "3–5 часов в неделю",
    skills: [] as string[], experience: "", desired_path: "Хочу быть активнее", motivation: "", personal_data_consent: false
  });
  const steps = ["О Вас", "Ваш путь", "Направления", "Потенциал", "Готово"];
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm((current) => ({ ...current, [key]: value }));
  const toggle = (key: "departments" | "directions" | "skills", value: string) => set(key, form[key].includes(value) ? form[key].filter((item) => item !== value) : [...form[key], value]);
  const visibleDirections = form.departments.length === 1 ? form.departments[0] === "Внутренние связи" ? internalDirections : externalDirections : [...internalDirections, ...externalDirections];
  const canContinue = [
    Boolean(form.first_name.trim() && form.last_name.trim() && Number(form.age) >= 14 && form.phone.trim().length >= 7 && form.city.trim()),
    Boolean(form.education_work.trim() && form.occupation.trim() && form.experience.trim()),
    Boolean(form.departments.length && form.directions.length),
    Boolean(form.skills.length && form.available_time && form.desired_path),
    Boolean(form.motivation.trim().length >= 10 && form.personal_data_consent)
  ][step];

  const goToStep = (nextStep: number) => {
    setError(null);
    (document.activeElement as HTMLElement | null)?.blur();
    setStep(nextStep);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const submit = async () => {
    setSaving(true); setError(null);
    try {
      await api("/api/registration", { method: "POST", body: JSON.stringify({ ...form, age: Number(form.age) }) });
      haptic.success(); onComplete();
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 409) {
        haptic.success();
        onComplete();
        return;
      }
      haptic.error();
      setError(requestError instanceof Error ? requestError.message : "Не удалось отправить анкету.");
      window.setTimeout(() => document.querySelector(".form-error")?.scrollIntoView({ block: "center", behavior: "smooth" }), 80);
    } finally { setSaving(false); }
  };

  return (
    <main className="registration page-shell">
      <div className="registration-header">
        <BrandLogo />
        <span>Анкета участника</span>
      </div>
      <div className="registration-progress" aria-label={`Шаг ${step + 1} из ${steps.length}: ${steps[step]}`}>
        <div className="registration-progress__header">
          <span>Шаг {step + 1} из {steps.length}</span>
          <strong>{steps[step]}</strong>
        </div>
        <div className="registration-progress__track" aria-hidden="true">
          {steps.map((label, index) => <span className={index <= step ? "is-active" : ""} key={label} />)}
        </div>
      </div>
      <section className="registration-card" key={step}>
        {step === 0 && <div className="form-stack"><FormIntro icon={<UserRound />} title="Давайте познакомимся" text="Основная информация для Вашего профиля в ЭРА." /><div className="field-row"><Field label="Имя"><input autoComplete="given-name" value={form.first_name} onChange={(event) => set("first_name", event.target.value)} /></Field><Field label="Фамилия"><input autoComplete="family-name" value={form.last_name} onChange={(event) => set("last_name", event.target.value)} /></Field></div><div className="field-row field-row--age"><Field label="Возраст"><input inputMode="numeric" type="number" min="14" max="100" value={form.age} onChange={(event) => set("age", event.target.value)} placeholder="18" /></Field><Field label="Телефон"><input autoComplete="tel" inputMode="tel" type="tel" value={form.phone} onChange={(event) => set("phone", event.target.value)} placeholder="+374..." /></Field></div><Field label="Город"><input autoComplete="address-level2" value={form.city} onChange={(event) => set("city", event.target.value)} placeholder="Ереван" /></Field></div>}
        {step === 1 && <div className="form-stack"><FormIntro icon={<Target />} title="Где Вы сейчас" text="Не нужно идеальное резюме — расскажите коротко и по делу." /><Field label="Учёба или работа"><input value={form.education_work} onChange={(event) => set("education_work", event.target.value)} placeholder="Университет, школа или компания" /></Field><Field label="Чем Вы занимаетесь"><textarea rows={3} value={form.occupation} onChange={(event) => set("occupation", event.target.value)} placeholder="Расскажите коротко о себе" /></Field><Field label="Опыт участия"><textarea rows={3} value={form.experience} onChange={(event) => set("experience", event.target.value)} placeholder="Проекты, мероприятия, волонтёрство — или пока без опыта" /></Field></div>}
        {step === 2 && <div className="form-stack"><FormIntro icon={<UsersRound />} title="Выберите направление" text="Можно выбрать оба департамента и несколько направлений." /><Field label="Департаменты"><ChoiceGrid values={["Внутренние связи", "Внешние связи"]} selected={form.departments} onToggle={(value) => toggle("departments", value)} multiple /></Field><Field label="Направления"><ChoiceGrid values={visibleDirections} selected={form.directions} onToggle={(value) => toggle("directions", value)} multiple /></Field></div>}
        {step === 3 && <div className="form-stack"><FormIntro icon={<Sparkles />} title="Ваш потенциал" text="Ответы помогут предлагать подходящие задачи и возможности." /><Field label="Сколько времени Вы готовы уделять"><ChoiceGrid values={["1–2 часа в неделю", "3–5 часов в неделю", "1 час в день", "Готов активно включаться"]} selected={[form.available_time]} onToggle={(value) => set("available_time", value)} /></Field><Field label="Навыки и интересы"><ChoiceGrid values={skillOptions} selected={form.skills} onToggle={(value) => toggle("skills", value)} multiple /></Field><Field label="Как Вы хотите начать"><select value={form.desired_path} onChange={(event) => set("desired_path", event.target.value)}><option>Просто участником</option><option>Хочу быть активнее</option><option>Хочу помогать команде</option><option>Хочу создавать проекты</option><option>В будущем хочу стать лидером</option></select></Field></div>}
        {step === 4 && <div className="form-stack"><FormIntro icon={<Check />} title="Почти готово" text="Одного-двух честных предложений будет достаточно." /><Field label="Почему Вам важно быть частью ЭРА"><textarea minLength={10} rows={4} value={form.motivation} onChange={(event) => set("motivation", event.target.value)} placeholder="Напишите не менее 10 символов" /></Field><label className="consent-row"><input type="checkbox" checked={form.personal_data_consent} onChange={(event) => set("personal_data_consent", event.target.checked)} /><span><strong>Согласие на обработку данных</strong><small>Данные нужны для регистрации, связи, мероприятий и Вашего портфолио внутри ЭРА.</small></span></label>{error && <p className="form-error" role="alert">{error}</p>}</div>}
      </section>
      <div className="registration-actions">{step > 0 && <button className="button button--ghost" onClick={() => goToStep(step - 1)}><ArrowLeft size={18} />Назад</button>}<button className="button button--primary" disabled={!canContinue || saving} onClick={() => step < steps.length - 1 ? goToStep(step + 1) : void submit()}>{saving ? <><LoaderCircle className="spin" size={18} />Сохраняем</> : step < steps.length - 1 ? <>Продолжить<ArrowRight size={18} /></> : <>Отправить<Send size={18} /></>}</button></div>
    </main>
  );
}

function Modal({ title, onClose, children, full = false }: { title: string; onClose: () => void; children: ReactNode; full?: boolean }) {
  return <div className="modal-backdrop" role="dialog" aria-modal="true"><section className={full ? "modal modal--full" : "modal"}><header><button className="icon-button" onClick={onClose} aria-label="Закрыть"><X size={20} /></button><h2>{title}</h2><span /></header><div className="modal-body">{children}</div></section></div>;
}

function PageTitle({ eyebrow, title, text }: { eyebrow: string; title: string; text: string }) {
  return <header className="page-title"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{text}</p></header>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

function ChoiceGrid({ values, selected, onToggle, multiple = false }: { values: string[]; selected: string[]; onToggle: (value: string) => void; multiple?: boolean }) {
  return <div className="choice-grid">{values.map((value) => <button type="button" key={value} className={selected.includes(value) ? "choice is-selected" : "choice"} onClick={() => onToggle(value)}>{selected.includes(value) && <Check size={14} />}{value}{multiple && selected.includes(value) ? null : null}</button>)}</div>;
}

function FormIntro({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return <div className="form-intro"><span>{icon}</span><div><h2>{title}</h2><p>{text}</p></div></div>;
}

function EmptyState({ icon, title, text, action }: { icon: ReactNode; title: string; text: string; action?: ReactNode }) {
  return <div className="empty-state"><span>{icon}</span><h3>{title}</h3><p>{text}</p>{action}</div>;
}

function EmptyInline({ text }: { text: string }) {
  return <div className="empty-inline"><CalendarDays size={18} /><span>{text}</span></div>;
}

function CardSkeleton() {
  return <div className="card-skeleton"><span /><span /><span /></div>;
}
