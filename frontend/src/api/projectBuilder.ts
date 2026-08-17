import type { ProjectQuestion } from "../types/project";
import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

function devTelegramId(): number | undefined {
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

async function token(): Promise<string> {
  if (!tokenPromise) {
    tokenPromise = authenticate(getInitData(), devTelegramId())
      .then((result) => result.token)
      .catch((error) => {
        tokenPromise = null;
        throw error;
      });
  }
  return tokenPromise;
}

export async function fetchProjectBuilderQuestions(): Promise<ProjectQuestion[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/project-builder/questions`);
  if (!response.ok) {
    throw new Error("project_builder_questions_unavailable");
  }
  return (await response.json()) as ProjectQuestion[];
}

export async function assistProjectAnswer(
  questionKey: string,
  answer: string,
  operation: "formulate" | "shorten" | "improve",
): Promise<string> {
  const sessionToken = await token();
  const response = await fetch(`${API_BASE_URL}/api/v1/project-builder/assist`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${sessionToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question_key: questionKey, answer, operation }),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // Never expose auth material or response bodies in console logs.
    }
    throw new ApiError(response.status, detail);
  }
  return ((await response.json()) as { text: string }).text;
}
