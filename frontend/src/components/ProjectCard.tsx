import type { ProjectSummary } from "../types/project";
import { Card } from "./Card";
import { ChevronRightIcon } from "./icons";
import { StatusBadge } from "./StatusBadge";
import { projectStatusLabel } from "../screens/projects/statusLabels";

interface ProjectCardProps {
  project: ProjectSummary;
  onClick: () => void;
  progressPercent?: number;
  teamCount?: number;
  nextStep?: string | null;
}

export function ProjectCard({ project, onClick, progressPercent, teamCount, nextStep }: ProjectCardProps) {
  return (
    <Card interactive onClick={onClick} ariaLabel={`${project.title}. Открыть проект`}>
      <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", justifyContent: "space-between" }}>
            <strong style={{ fontSize: "var(--era-text-lg)", lineHeight: 1.25, overflowWrap: "anywhere" }}>{project.title}</strong>
            <StatusBadge label={projectStatusLabel(project.status)} tone="neutral" />
          </div>
          {project.short_description && <p style={{ margin: "0.4rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.45 }}>{project.short_description}</p>}
          {(progressPercent !== undefined || teamCount !== undefined) && (
            <div style={{ display: "flex", gap: "0.9rem", marginTop: "0.75rem", fontSize: "var(--era-text-sm)" }}>
              {progressPercent !== undefined && <strong>{Math.round(progressPercent)}% готово</strong>}
              {teamCount !== undefined && <span className="era-muted">{teamCount} в команде</span>}
            </div>
          )}
          {nextStep && <p style={{ margin: "0.65rem 0 0", paddingTop: "0.65rem", borderTop: "1px solid var(--era-border)", fontSize: "var(--era-text-sm)" }}><span className="era-muted">Следующий шаг: </span><strong>{nextStep}</strong></p>}
        </div>
        <ChevronRightIcon width={20} height={20} style={{ color: "var(--era-text-muted)", flexShrink: 0, marginTop: 2 }} />
      </div>
    </Card>
  );
}
