import { ProjectDetail } from "./ProjectDetail";
import { ProjectsList } from "./ProjectsList";

interface ProjectsSectionProps {
  initialProjectId?: number | null;
}

export function ProjectsSection({ initialProjectId = null }: ProjectsSectionProps) {
  const openProject = (projectId: number) => {
    window.location.hash = `#/projects/${projectId}`;
  };

  if (initialProjectId === null) {
    return <ProjectsList onSelect={openProject} />;
  }

  return (
    <ProjectDetail
      projectId={initialProjectId}
      initialShowWorkspace={false}
      onBack={() => {
        if (window.history.length > 1) window.history.back();
        else window.location.hash = "#/projects";
      }}
    />
  );
}
