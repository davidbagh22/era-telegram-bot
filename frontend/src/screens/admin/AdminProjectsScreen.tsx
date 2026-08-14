import { useState } from "react";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { ProjectsSection } from "../projects/ProjectsSection";
import { ProjectModerationPanel } from "./projects/ProjectModerationPanel";
import { TeamPostsPanel } from "./projects/TeamPostsPanel";

type ProjectsSectionKey = "create" | "moderation" | "team-posts";

const SECTIONS: { value: ProjectsSectionKey; label: string; description: string; icon: string }[] = [
  { value: "create", label: "Создать проект", description: "Запустить тот же пошаговый конструктор, что доступен участникам", icon: "＋" },
  { value: "moderation", label: "Проекты на рассмотрении", description: "Прочитать проект целиком и принять решение", icon: "✓" },
  { value: "team-posts", label: "Поиск команды", description: "Проверить объявления о наборе людей в проекты", icon: "◎" },
];

export function AdminProjectsScreen() {
  const [section, setSection] = useState<ProjectsSectionKey | null>(null);

  if (!section) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <Card gradient>
          <p style={{ margin: "0 0 0.25rem", color: "rgba(255,255,255,0.72)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Проекты</p>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>Создать, проверить, собрать команду</h2>
          <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.82)" }}>Три разных действия больше не спрятаны за переключателями — выберите, что нужно сделать сейчас.</p>
        </Card>
        {SECTIONS.map((item) => (
          <ActionCell key={item.value} title={item.label} description={item.description} leading={item.icon} onClick={() => setSection(item.value)} />
        ))}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={() => setSection(null)} style={{ alignSelf: "flex-start" }}>← К проектам</button>
      <div>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{SECTIONS.find((item) => item.value === section)?.label}</h2>
        <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)" }}>{SECTIONS.find((item) => item.value === section)?.description}</p>
      </div>
      {section === "create" && <ProjectsSection />}
      {section === "moderation" && <ProjectModerationPanel />}
      {section === "team-posts" && <TeamPostsPanel />}
    </div>
  );
}
