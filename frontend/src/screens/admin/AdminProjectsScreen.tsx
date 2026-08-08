import { useState } from "react";
import { PillTabs } from "../../components/PillTabs";
import { ProjectModerationPanel } from "./projects/ProjectModerationPanel";
import { TeamPostsPanel } from "./projects/TeamPostsPanel";

type ProjectsSection = "moderation" | "team-posts";

const SECTIONS: { value: ProjectsSection; label: string }[] = [
  { value: "moderation", label: "На рассмотрении" },
  { value: "team-posts", label: "Ищем команду" },
];

export function AdminProjectsScreen() {
  const [section, setSection] = useState<ProjectsSection>("moderation");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <PillTabs options={SECTIONS} active={section} onChange={setSection} />
      {section === "moderation" && <ProjectModerationPanel />}
      {section === "team-posts" && <TeamPostsPanel />}
    </div>
  );
}
