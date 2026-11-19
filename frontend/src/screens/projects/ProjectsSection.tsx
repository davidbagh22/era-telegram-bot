import { useEffect, useState } from "react";
import { MediaRequestButton } from "../../components/MediaRequestButton";
import { ProjectDetail } from "./ProjectDetail";
import { ProjectsList } from "./ProjectsList";

interface ProjectsSectionProps {
  initialProjectId?: number | null;
}

// The list<->detail toggle itself, with no page wrapper or heading --
// extracted from ProjectsScreen.tsx (2026-08 redesign brief section 16)
// so it can be reused both as its own standalone screen (ProjectsScreen,
// still used for admin/leader deep links straight into a project) and as
// one of Activity's sub-sections (ActivityScreen no longer has a
// top-level "Проекты" tab of its own -- see FloatingNav.tsx).
export function ProjectsSection({ initialProjectId = null }: ProjectsSectionProps) {
  const [selectedId, setSelectedId] = useState<number | null>(initialProjectId);

  useEffect(() => {
    setSelectedId(initialProjectId);
  }, [initialProjectId]);

  if (selectedId === null) {
    return <ProjectsList onSelect={(id) => {
      setSelectedId(id);
      const prefix = window.location.hash.startsWith("#/admin") ? "admin/projects/" : "projects/";
      window.location.hash = "#/" + prefix + id;
    }} />;
  }
  return (
    <div style={{ display: "grid", gap: "0.75rem" }}>
      <ProjectDetail
        key={selectedId}
        projectId={selectedId}
        onBack={() => {
          setSelectedId(null);
          window.location.hash = window.location.hash.startsWith("#/admin") ? "#/admin" : "#/projects";
        }}
      />
      <MediaRequestButton sourceType="project" sourceId={selectedId} />
    </div>
  );
}
