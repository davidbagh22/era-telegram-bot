import { fetchEvents, fetchProjects, fetchTasks } from "../api/client";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { SkeletonCard } from "../components/Skeleton";
import { ChevronRightIcon, EventIcon, ProjectsIcon, TaskIcon } from "../components/icons";
import { useAsync } from "../hooks/useAsync";

export function NotificationsScreen() {
  const events = useAsync(() => fetchEvents("mine"), []);
  const tasks = useAsync(() => fetchTasks("mine"), []);
  const projects = useAsync(() => fetchProjects("mine"), []);

  const back = () => {
    if (window.history.length > 1) window.history.back();
    else window.location.hash = "#/home";
  };

  const loading = events.status === "loading" || tasks.status === "loading" || projects.status === "loading";
  const items = [
    ...(events.status === "ready" ? events.data.slice(0, 5).map((item) => ({ key: `event-${item.id}`, title: item.title, detail: `${item.event_date} · ${item.event_time} · ${item.location}`, route: `events/${item.id}`, kind: "Событие", Icon: EventIcon })) : []),
    ...(tasks.status === "ready" ? tasks.data.filter((item) => item.status !== "completed").slice(0, 5).map((item) => ({ key: `task-${item.id}`, title: item.title, detail: `Срок ${item.deadline} · ${item.points} баллов`, route: `tasks/${item.id}`, kind: "Задача", Icon: TaskIcon })) : []),
    ...(projects.status === "ready" ? projects.data.slice(0, 5).map((item) => ({ key: `project-${item.id}`, title: item.title, detail: item.admin_comment || item.short_description, route: `projects/${item.id}`, kind: "Проект", Icon: ProjectsIcon })) : []),
  ];

  return (
    <div className="era-page era-page-shell">
      <PageHeader title="Уведомления" eyebrow="Актуально сейчас" subtitle="Здесь только реальные текущие объекты из системы. Нажатие всегда ведёт прямо к событию, задаче или проекту." onBack={back} />
      {loading && <><SkeletonCard /><SkeletonCard /></>}
      {!loading && items.length === 0 && <EmptyState title="Новых действий нет" description="Когда появится регистрация, задача или изменение по проекту, связанный объект будет доступен здесь." />}
      {!loading && items.map(({ key, title, detail, route, kind, Icon }) => (
        <Card key={key} interactive onClick={() => { window.location.hash = `#/${route}`; }} ariaLabel={`${kind}: ${title}. Открыть`}>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <span style={{ width: 42, height: 42, borderRadius: 14, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--era-red)", background: "var(--era-tint-red)", flexShrink: 0 }}><Icon width={20} height={20} /></span>
            <div style={{ flex: 1, minWidth: 0 }}><p className="era-kicker">{kind}</p><strong style={{ display: "block", marginTop: 2, overflowWrap: "anywhere" }}>{title}</strong>{detail && <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{detail}</p>}</div>
            <ChevronRightIcon width={20} height={20} style={{ color: "var(--era-text-muted)", flexShrink: 0 }} />
          </div>
        </Card>
      ))}
    </div>
  );
}
