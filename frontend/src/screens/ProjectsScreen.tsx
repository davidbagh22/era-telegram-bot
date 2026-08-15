import { PageHeader } from "../components/PageHeader";
import { ProjectsSection } from "./projects/ProjectsSection";

interface ProjectsScreenProps { initialProjectId?: number | null; }

export function ProjectsScreen({ initialProjectId = null }: ProjectsScreenProps) {
  return (
    <div className="era-page era-page-shell">
      {initialProjectId === null && <PageHeader title="Проекты" eyebrow="Реальные инициативы" subtitle="Создавайте идеи, собирайте команду и доводите результат до запуска." />}
      <ProjectsSection initialProjectId={initialProjectId} />
    </div>
  );
}
