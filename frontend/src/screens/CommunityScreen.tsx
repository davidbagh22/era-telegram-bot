import { useEffect, useMemo, useState } from "react";
import { fetchCommunityUsers } from "../api/communityUsers";
import { fetchProjects } from "../api/client";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { ProjectCard } from "../components/ProjectCard";
import { SkeletonList } from "../components/Skeleton";
import { ChevronRightIcon, CommunityIcon, ProjectsIcon, SearchIcon, SparkIcon, TeamIcon } from "../components/icons";
import { useAsync } from "../hooks/useAsync";

export type CommunitySection = "people" | "team" | "projects" | "interests";

interface CommunityScreenProps {
  initialSection?: CommunitySection | null;
}

const SECTIONS: { value: CommunitySection; label: string; description: string; Icon: typeof CommunityIcon }[] = [
  { value: "people", label: "Люди", description: "Найти участника по имени, направлению и активности", Icon: CommunityIcon },
  { value: "team", label: "Ищу команду", description: "Открытые проекты, где можно включиться в работу", Icon: TeamIcon },
  { value: "projects", label: "Проекты", description: "Инициативы сообщества, доступные для участия", Icon: ProjectsIcon },
  { value: "interests", label: "Интересы", description: "Найти людей по направлениям, которые им действительно интересны", Icon: SparkIcon },
];

export function CommunityScreen({ initialSection = null }: CommunityScreenProps) {
  const [section, setSection] = useState<CommunitySection | null>(initialSection);

  useEffect(() => setSection(initialSection), [initialSection]);

  const openSection = (value: CommunitySection) => {
    setSection(value);
    window.location.hash = `#/community/${value}`;
  };
  const back = () => {
    setSection(null);
    window.location.hash = "#/community";
  };

  if (section === "people") return <PeopleDirectory onBack={back} />;
  if (section === "interests") return <InterestsDirectory onBack={back} />;
  if (section === "team" || section === "projects") return <OpenProjectsDirectory title={section === "team" ? "Ищу команду" : "Проекты сообщества"} subtitle={section === "team" ? "Только реальные открытые проекты. Откройте карточку и посмотрите рабочую зону и роли." : "Проекты, к которым можно присоединиться прямо сейчас."} onBack={back} />;

  return (
    <div className="era-page era-page-shell">
      <PageHeader title="Сообщество" eyebrow="Люди для взаимодействия" subtitle="Это не социальная сеть. Здесь находят людей, команды и проекты для реальной работы." />
      <div className="era-grid-2">
        {SECTIONS.map(({ value, label, description, Icon }) => (
          <Card key={value} interactive onClick={() => openSection(value)} ariaLabel={`${label}. Открыть`} style={{ minHeight: 160 }}>
            <span style={{ width: 42, height: 42, borderRadius: 14, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--era-tint-red)", color: "var(--era-red)" }}><Icon width={21} height={21} /></span>
            <strong style={{ display: "block", marginTop: "0.85rem", fontSize: "var(--era-text-lg)" }}>{label}</strong>
            <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", lineHeight: 1.45 }}>{description}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}

function PeopleDirectory({ onBack }: { onBack: () => void }) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const timer = window.setTimeout(() => setDebounced(query), 300); return () => window.clearTimeout(timer); }, [query]);
  const state = useAsync(() => fetchCommunityUsers(debounced), [debounced]);

  return (
    <div className="era-page era-page-shell">
      <PageHeader title="Люди" eyebrow="Сообщество ЭРА" subtitle="Публично показываем только данные, нужные для взаимодействия. Телефон, email и регистрационная анкета здесь не раскрываются." onBack={onBack} />
      <label style={{ position: "relative" }}><span style={{ position: "absolute", left: 14, top: 13, color: "var(--era-text-muted)", zIndex: 1 }}><SearchIcon width={19} height={19} /></span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Имя или Telegram" style={{ paddingLeft: 44 }} /></label>
      {state.status === "loading" && <SkeletonList count={4} />}
      {state.status === "error" && <EmptyState title="Люди не загрузились" description="Проверьте соединение и попробуйте открыть раздел снова." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState title="Никого не нашли" description="Измените запрос — личные данные и скрытые анкеты в поиск не попадают." />}
      {state.status === "ready" && <div style={{ display: "grid", gap: "0.7rem" }}>{state.data.map((user) => <PersonCard key={user.id} user={user} />)}</div>}
    </div>
  );
}

function InterestsDirectory({ onBack }: { onBack: () => void }) {
  const state = useAsync(() => fetchCommunityUsers(), []);
  const [interest, setInterest] = useState<string | null>(null);
  const interests = useMemo(() => state.status === "ready" ? Array.from(new Set(state.data.flatMap((user) => user.directions))).sort() : [], [state]);
  const people = state.status === "ready" ? state.data.filter((user) => !interest || user.directions.includes(interest)) : [];
  return (
    <div className="era-page era-page-shell">
      <PageHeader title="Интересы" eyebrow="Кто чем горит" subtitle="Направления берутся из реальных профилей участников — без придуманных тегов." onBack={onBack} />
      {state.status === "loading" && <SkeletonList count={3} />}
      {state.status === "error" && <EmptyState title="Интересы не загрузились" description="Попробуйте открыть раздел снова." />}
      {state.status === "ready" && interests.length === 0 && <EmptyState title="Интересы ещё не заполнены" description="Они появятся, когда участники выберут направления в ЭРА." />}
      {interests.length > 0 && <select aria-label="Интерес" value={interest ?? ""} onChange={(event) => setInterest(event.target.value || null)}><option value="">Все направления</option>{interests.map((item) => <option key={item} value={item}>{item}</option>)}</select>}
      {interest && <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{people.length} участников указали «{interest}»</p>}
      <div style={{ display: "grid", gap: "0.7rem" }}>{people.map((user) => <PersonCard key={user.id} user={user} />)}</div>
    </div>
  );
}

function OpenProjectsDirectory({ title, subtitle, onBack }: { title: string; subtitle: string; onBack: () => void }) {
  const state = useAsync(() => fetchProjects("open"), []);
  return (
    <div className="era-page era-page-shell">
      <PageHeader title={title} eyebrow="Сообщество ЭРА" subtitle={subtitle} onBack={onBack} />
      {state.status === "loading" && <SkeletonList count={3} />}
      {state.status === "error" && <EmptyState title="Проекты не загрузились" description="Попробуйте открыть раздел снова." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState title="Открытых проектов пока нет" description="Когда команда откроет набор, он появится здесь автоматически." actionLabel="Создать свой проект" onAction={() => { window.location.hash = "#/projects"; }} />}
      {state.status === "ready" && <div style={{ display: "grid", gap: "0.75rem" }}>{state.data.map((project) => <ProjectCard key={project.id} project={project} onClick={() => { window.location.hash = `#/projects/${project.id}`; }} />)}</div>}
    </div>
  );
}

function PersonCard({ user }: { user: import("../api/communityUsers").CommunityUser }) {
  const initials = user.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
  const activity = user.events_attended + user.project_memberships + user.tasks_completed;
  return (
    <Card interactive onClick={() => { window.location.hash = `#/users/${user.id}`; }} ariaLabel={`${user.name}. Открыть публичный профиль`}>
      <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
        <span style={{ width: 48, height: 48, borderRadius: "50%", display: "grid", placeItems: "center", background: "var(--era-bg-subtle)", fontWeight: 850, flexShrink: 0 }}>{initials || "Э"}</span>
        <div style={{ flex: 1, minWidth: 0 }}><strong style={{ display: "block", overflowWrap: "anywhere" }}>{user.name}</strong><span style={{ display: "block", marginTop: 2, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{user.participation_label}{user.directions[0] ? ` · ${user.directions[0]}` : ""}</span><span style={{ display: "block", marginTop: 4, color: "var(--era-text-muted)", fontSize: "0.7rem" }}>{activity > 0 ? `${activity} подтверждённых действий` : "Активность ещё формируется"}</span></div>
        <ChevronRightIcon width={20} height={20} style={{ color: "var(--era-text-muted)", flexShrink: 0 }} />
      </div>
    </Card>
  );
}
