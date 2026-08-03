import { useState } from "react";
import { ProjectDetail } from "./projects/ProjectDetail";
import { ProjectsList } from "./projects/ProjectsList";

export function ProjectsScreen() {
  const [selectedId, setSelectedId] = useState<number | null>(null);

  return (
    <div style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
        Проекты
      </h1>
      {selectedId === null ? (
        <ProjectsList onSelect={setSelectedId} />
      ) : (
        <ProjectDetail projectId={selectedId} onBack={() => setSelectedId(null)} />
      )}
    </div>
  );
}
