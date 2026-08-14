import { Card } from "../components/Card";
import { ProjectsIcon } from "../components/icons";
import { ProjectsSection } from "./projects/ProjectsSection";

interface ProjectsScreenProps {
  initialProjectId?: number | null;
}

export function ProjectsScreen({ initialProjectId = null }: ProjectsScreenProps) {
  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Card gradient style={{ position: "relative", overflow: "hidden", minHeight: 154 }}>
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            right: -42,
            top: -38,
            width: 158,
            height: 158,
            borderRadius: "50%",
            border: "1px solid rgba(255,255,255,0.16)",
            background: "rgba(255,255,255,0.08)",
          }}
        />
        <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <span
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "rgba(255,255,255,0.14)",
            }}
            aria-hidden="true"
          >
            <ProjectsIcon width={22} height={22} />
          </span>
          <div>
            <p
              style={{
                margin: "0 0 0.35rem",
                color: "rgba(255,255,255,0.68)",
                fontSize: "var(--era-text-xs)",
                fontWeight: 800,
                textTransform: "uppercase",
              }}
            >
              Рабочая зона
            </p>
            <h1 style={{ margin: 0, fontSize: "var(--era-text-3xl)", lineHeight: 1.08 }}>
              Проекты
            </h1>
            <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.78)", maxWidth: 280 }}>
              Инициативы, команда, задачи и вклад в одном месте.
            </p>
          </div>
        </div>
      </Card>
      <ProjectsSection initialProjectId={initialProjectId} />
    </div>
  );
}
