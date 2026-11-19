import { EditorialHero } from "../components/EditorialHero";
import { ProjectsIcon } from "../components/icons";
import { ProjectsSection } from "./projects/ProjectsSection";

interface ProjectsScreenProps {
  initialProjectId?: number | null;
}

export function ProjectsScreen({ initialProjectId = null }: ProjectsScreenProps) {
  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <EditorialHero
        eyebrow="Проекты ЭРА"
        title="Проекты"
        description="Идея, команда, задачи и вклад — в одном месте."
        glow="hot"
      >
        <span
          aria-hidden="true"
          style={{
            width: 44,
            height: 44,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--era-tint-gold)",
            color: "var(--era-gold-ink)",
          }}
        >
          <ProjectsIcon width={22} height={22} />
        </span>
      </EditorialHero>
      {!initialProjectId && <>
        <button className="era-btn-primary" onClick={() => { window.location.hash = "#/ideas"; }}>Предложить идею</button>
        <div style={{ display: "flex", gap: 8 }}>
          <button style={{ flex: 1 }} onClick={() => { window.location.hash = "#/teams"; }}>Команды</button>
          <button style={{ flex: 1 }} onClick={() => { window.location.hash = "#/tasks"; }}>Задачи</button>
        </div>
      </>}
      <ProjectsSection initialProjectId={initialProjectId} />
    </div>
  );
}
