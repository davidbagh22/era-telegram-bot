import { ProjectsSection } from "./projects/ProjectsSection";

interface ProjectsScreenProps {
  initialProjectId?: number | null;
}

// Standalone full-page wrapper around ProjectsSection -- used only for
// admin/leader deep links that land straight on one project (App.tsx),
// bypassing tab navigation entirely since Admin/Leader Mode has no
// participant-style bottom nav. Participants reach the same content
// through Activity's "Проекты" action card instead (ActivityScreen).
export function ProjectsScreen({ initialProjectId = null }: ProjectsScreenProps) {
  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
        Проекты
      </h1>
      <ProjectsSection initialProjectId={initialProjectId} />
    </div>
  );
}
