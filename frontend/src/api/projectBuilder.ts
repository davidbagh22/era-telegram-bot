import type { ProjectQuestion } from "../types/project";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchProjectBuilderQuestions(): Promise<ProjectQuestion[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/project-builder/questions`);
  if (!response.ok) {
    throw new Error("project_builder_questions_unavailable");
  }
  return (await response.json()) as ProjectQuestion[];
}
